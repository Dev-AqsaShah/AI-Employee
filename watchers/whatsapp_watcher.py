"""
whatsapp_watcher.py — WhatsApp Monitor & Auto-Sender for AI Employee (Gold Tier)

Uses Playwright persistent browser context on WhatsApp Web.
  - MONITOR mode: detects new messages → saves to Inbox/
  - SEND mode:    watches Approved/WHATSAPP_REPLY_*.md → sends replies

Setup (one-time):
    python watchers/whatsapp_watcher.py --setup
    (browser opens, scan QR code, session saved automatically)

Usage:
    python watchers/whatsapp_watcher.py              # Watch + send loop
    python watchers/whatsapp_watcher.py --setup      # Save QR session
    python watchers/whatsapp_watcher.py --check-now  # Check messages once
    python watchers/whatsapp_watcher.py --send-now   # Send approved replies once
    python watchers/whatsapp_watcher.py --dry-run    # Test without sending
"""

import os
import re
import sys
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WhatsAppWatcher] %(levelname)s: %(message)s",
)
logger = logging.getLogger("WhatsAppWatcher")

# ── Config ────────────────────────────────────────────────────────────────────
VAULT_PATH    = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
SESSION_PATH  = Path(os.getenv("WHATSAPP_SESSION_PATH", "credentials/whatsapp_session"))
BROWSER_DIR   = SESSION_PATH / "browser_data"
DRY_RUN       = os.getenv("DRY_RUN", "false").lower() == "true"

INBOX_DIR    = VAULT_PATH / "Inbox"
APPROVED_DIR = VAULT_PATH / "Approved"
DONE_DIR     = VAULT_PATH / "Done"
LOGS_DIR     = VAULT_PATH / "Logs"

WHATSAPP_URL = "https://web.whatsapp.com"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(action: str, details: str):
    today = datetime.now().strftime("%Y-%m-%d")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = f"[{datetime.now(timezone.utc).isoformat()}] [WhatsApp] {action}: {details}\n"
    with open(LOGS_DIR / f"{today}.log", "a", encoding="utf-8") as f:
        f.write(entry)


def _safe_name(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "_", text)[:40]


def _launch(p, headless: bool = False):
    """Launch persistent context — preserves IndexedDB for WhatsApp Web session."""
    BROWSER_DIR.mkdir(parents=True, exist_ok=True)
    # Remove stale lockfiles left by crashed processes
    for lf in ["lockfile", "SingletonLock", "SingletonCookie"]:
        lock_path = BROWSER_DIR / lf
        if lock_path.exists():
            try:
                lock_path.unlink()
            except Exception:
                pass
    context = p.chromium.launch_persistent_context(
        str(BROWSER_DIR),
        channel="chrome",   # Use system Chrome — more stable than Playwright's Chromium
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--window-position=-32000,-32000",
            "--window-size=1280,900",
        ],
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        locale="en-US",
        timezone_id="Asia/Karachi",
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return context


def _wait_for_home(page, timeout_sec: int = 90):
    """Wait until WhatsApp Web chat list is visible."""
    selectors = [
        "#pane-side",
        "div[aria-label='Chat list']",
        "[data-testid='chat-list']",
        "[data-testid='chat-list-search']",
        "[aria-label='Search input textbox']",
    ]
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    logger.info(f"WhatsApp home loaded ({sel})")
                    return True
            except Exception:
                pass
        time.sleep(2)
    return False


def extract_reply(filepath: Path) -> tuple:
    """Return (contact, message) from approved reply file."""
    raw = filepath.read_text(encoding="utf-8")
    contact_m = re.search(r"^contact:\s*(.+)$", raw, re.MULTILINE)
    contact = contact_m.group(1).strip() if contact_m else ""
    msg_m = re.search(r"##\s+Reply Content\s*\n(.*?)(?:\n---|\Z)", raw, flags=re.DOTALL | re.IGNORECASE)
    if msg_m:
        message = msg_m.group(1).strip()
    else:
        message = re.sub(r"^---.*?---\s*", "", raw, flags=re.DOTALL)
        message = re.sub(r"^[#>].*$", "", message, flags=re.MULTILINE)
        message = re.sub(r"\n{3,}", "\n\n", message).strip()
    return contact, message


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup_session():
    """Open WhatsApp Web for QR scan. Works on both desktop and headless EC2."""
    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright not installed.")
        print("Run: pip install playwright && playwright install chromium")
        return False

    import platform
    is_linux = platform.system() == "Linux"

    print("\n" + "=" * 55)
    print("WHATSAPP WEB SESSION SETUP")
    print("=" * 55)
    if is_linux:
        print("EC2/Linux mode: QR code will be saved as qr_code.png")
        print("Download and scan it with your phone.")
    else:
        print("Browser will open — scan QR code with your phone.")
    print("=" * 55 + "\n")

    qr_path = Path("qr_code.png")

    try:
        with sync_playwright() as p:
            if is_linux:
                # Headless on Linux/EC2
                context = p.chromium.launch_persistent_context(
                    str(BROWSER_DIR),
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage",
                          "--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1280, "height": 900},
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                )
            else:
                context = _launch(p, headless=False)

            page = context.new_page()
            print("Opening https://web.whatsapp.com ...")
            page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=60000)

            if is_linux:
                # Wait for QR code to appear and save screenshot
                print("Waiting for QR code...")
                for i in range(60):
                    time.sleep(2)
                    # Check if QR appeared
                    qr_el = page.query_selector("canvas[aria-label='Scan this QR code to link a device'], [data-testid='qrcode'], canvas")
                    if qr_el:
                        qr_el.screenshot(path=str(qr_path))
                        print(f"\nQR code saved: {qr_path.absolute()}")
                        print("Download this file and scan with WhatsApp on your phone.")
                        print("  scp ubuntu@51.20.40.140:~/AI-Employee/qr_code.png .")
                        break
                    else:
                        page.screenshot(path=str(qr_path))
                        print(f"  Waiting... ({(i+1)*2}s) — QR screenshot saved to {qr_path}")

                # Wait for home to load (user scans QR)
                print("\nWaiting for you to scan QR (up to 3 minutes)...")
                loaded = _wait_for_home(page, timeout_sec=180)
                if loaded:
                    print("SUCCESS! WhatsApp connected. Session saved.")
                    _log("SETUP_COMPLETE", str(BROWSER_DIR))
                else:
                    page.screenshot(path=str(qr_path))
                    print(f"Timeout — check {qr_path} for current state.")
            else:
                print("Scan the QR code in the browser window...")
                loaded = _wait_for_home(page, timeout_sec=120)
                if loaded:
                    print("WhatsApp home loaded! Session saved.")
                else:
                    print("Timeout — session may still be saved.")
                input("\nPress Enter to save session and close: ")

            context.close()
            if qr_path.exists():
                qr_path.unlink(missing_ok=True)
            print(f"\nDone! Session: {BROWSER_DIR}")
            return True
    except Exception as e:
        print(f"\nERROR: {e}")
        return False


# ── Message Checker ───────────────────────────────────────────────────────────

def check_messages() -> list:
    """Open WhatsApp Web, find unread chats, return list of message dicts."""
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright not installed.")
        return []

    if not BROWSER_DIR.exists():
        logger.error("No session found. Run: python watchers/whatsapp_watcher.py --setup")
        return []

    messages = []
    seen_file = VAULT_PATH / ".processed_whatsapp_ids"
    seen_ids = set(seen_file.read_text(encoding="utf-8").splitlines()) if seen_file.exists() else set()

    debug_dir = Path("debug_screenshots")
    debug_dir.mkdir(exist_ok=True)

    try:
        with sync_playwright() as p:
            context = _launch(p, headless=False)
            page = context.new_page()
            logger.info("Opening WhatsApp Web (visible for setup)...")
            page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            loaded = _wait_for_home(page, timeout_sec=60)
            if not loaded:
                page.screenshot(path=str(debug_dir / "wa_error_login.png"))
                logger.error("WhatsApp home not loaded. Run --setup again.")
                context.close()
                return []

            time.sleep(2)
            page.screenshot(path=str(debug_dir / "wa_1_home.png"))
            logger.info("Scanning for unread chats...")

            # Find chats with unread badge — try multiple selectors
            chats = []
            for sel in [
                "[data-testid='cell-frame-container']",
                "div[role='listitem']",
                "#pane-side [tabindex='-1']",
                "#pane-side > div > div > div > div",
            ]:
                chats = page.query_selector_all(sel)
                if chats:
                    logger.info(f"Found {len(chats)} chats with: {sel}")
                    break
            logger.info(f"Chats visible: {len(chats)}")

            for chat in chats:
                try:
                    # Check for unread badge (green number)
                    # Check for unread badge (green number)
                    badge = None
                    for badge_sel in [
                        "[data-testid='icon-unread-count']",
                        "span[aria-label*='unread']",
                        "span.bg-icon-unread-count",
                    ]:
                        badge = chat.query_selector(badge_sel)
                        if badge:
                            break
                    if not badge:
                        continue

                    # Get contact name
                    name_el = None
                    for name_sel in [
                        "[data-testid='cell-frame-title']",
                        "span[title]",
                        "span[dir='auto']",
                    ]:
                        name_el = chat.query_selector(name_sel)
                        if name_el:
                            break
                    contact = name_el.inner_text().strip() if name_el else "Unknown"

                    # Groups allowed — don't skip them

                    chat_id = f"wa_{_safe_name(contact)}_{datetime.now().strftime('%Y%m%d')}"
                    if chat_id in seen_ids:
                        continue

                    chat.click()
                    time.sleep(3)

                    # Extract incoming messages using JavaScript (most reliable)
                    chat_texts = page.evaluate("""() => {
                        const texts = [];
                        // Get incoming messages only (message-in class)
                        const incomingRows = document.querySelectorAll(
                            '[data-testid="msg-container"]:not(.message-out), ' +
                            '.message-in [data-testid="msg-container"], ' +
                            'div[class*="message-in"]'
                        );
                        // Fallback: all message containers
                        const allRows = document.querySelectorAll('[data-testid="msg-container"]');
                        const rows = incomingRows.length > 0 ? incomingRows : allRows;
                        const last = Array.from(rows).slice(-10);
                        for (const row of last) {
                            // Try copyable-text attribute first (has sender + time info stripped)
                            const copyable = row.querySelector('.copyable-text');
                            if (copyable) {
                                const spans = copyable.querySelectorAll('span');
                                let txt = '';
                                for (const s of spans) {
                                    if (s.children.length === 0 && s.textContent.trim()) {
                                        txt += s.textContent.trim() + ' ';
                                    }
                                }
                                txt = txt.trim();
                                if (txt && txt.length > 1) { texts.push(txt); continue; }
                                // fallback to innerText
                                txt = copyable.innerText.trim();
                                if (txt) { texts.push(txt); continue; }
                            }
                            // Last resort: full row text
                            const full = row.innerText.trim();
                            if (full && full.length > 2) texts.push(full.slice(0, 400));
                        }
                        return texts;
                    }""")
                    if not chat_texts:
                        chat_texts = []

                    messages.append({"contact": contact, "messages": chat_texts, "chat_id": chat_id})
                    seen_ids.add(chat_id)
                    logger.info(f"New message from: {contact}")

                except Exception as e:
                    logger.warning(f"Chat read error: {e}")
                    continue

            context.close()
            seen_file.write_text("\n".join(seen_ids), encoding="utf-8")

    except Exception as e:
        logger.error(f"check_messages failed: {e}")
        _log("CHECK_ERROR", str(e)[:200])

    return messages


def save_to_inbox(msg: dict) -> Path:
    """Save a message dict to Inbox/ as markdown."""
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"WHATSAPP_{ts}_{_safe_name(msg['contact'])}.md"
    filepath = INBOX_DIR / filename

    lines = "\n".join(f"- {m}" for m in msg["messages"]) if msg["messages"] else "- (no text)"

    filepath.write_text(f"""---
type: whatsapp_message
contact: {msg['contact']}
received: {datetime.now(timezone.utc).isoformat()}
status: needs_action
---

# WhatsApp — {msg['contact']} — {datetime.now().strftime('%Y-%m-%d %H:%M')}

> **From:** {msg['contact']}
> **Received:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Messages

{lines}

---

## Instructions
- Run `/process-inbox` to let Claude draft a reply
- Reply file will appear in `Pending_Approval/WHATSAPP_REPLY_*.md`
""", encoding="utf-8")

    # Auto-draft a reply in Pending_Approval (requires human approval before sending)
    _draft_reply(msg, lines)

    _log("MESSAGE_SAVED", f"{msg['contact']} -> {filename}")
    logger.info(f"Saved: {filename}")
    return filepath


def _ai_draft_reply(contact: str, messages: list) -> str:
    """Use Claude API to generate a smart reply based on message content."""
    if not CLAUDE_AVAILABLE:
        return "(Claude unavailable — edit this reply before approving)"

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "(No ANTHROPIC_API_KEY — edit this reply before approving)"

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msgs_text = "\n".join(f"- {m}" for m in messages) if messages else "(no text)"

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": (
                    f"You are Aqsa. Write a WhatsApp reply AS Aqsa — in first person, her own voice.\n\n"
                    f"The person you are replying to: {contact}\n"
                    f"Their message(s):\n{msgs_text}\n\n"
                    f"Rules:\n"
                    f"- Write AS Aqsa, not as an AI or assistant\n"
                    f"- VERY IMPORTANT: If their message is in Roman Urdu, reply in Roman Urdu. If English, reply in English. Match their language exactly.\n"
                    f"- Reply directly to what they said — answer questions, respond to what they shared\n"
                    f"- Keep it short: 1-3 sentences like a real WhatsApp chat\n"
                    f"- No markdown, no formatting, plain text only\n"
                    f"- Sound natural and friendly, like texting a friend\n"
                    f"- Never say 'How can I help you' or sound like a bot or assistant"
                ),
            }],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning(f"Claude API error: {e}")
        return "(AI draft failed — edit this reply before approving)"


def _draft_reply(msg: dict, lines: str):
    """Auto-draft an AI reply in Pending_Approval — human must approve before sending."""
    pending_dir = VAULT_PATH / "Pending_Approval"
    pending_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d")
    safe = _safe_name(msg['contact'])
    filename = f"WHATSAPP_REPLY_{ts}_{safe}.md"
    filepath = pending_dir / filename

    if filepath.exists():
        return

    # Generate AI reply
    logger.info(f"Drafting AI reply for: {msg['contact']}")
    ai_reply = _ai_draft_reply(msg['contact'], msg.get('messages', []))

    filepath.write_text(f"""---
type: whatsapp_reply
contact: {msg['contact']}
drafted: {datetime.now(timezone.utc).isoformat()}
status: pending_approval
---

# WhatsApp Reply — {msg['contact']} — {ts}

> **To:** {msg['contact']}
> **Original message:**
{lines}

---

## Reply Content

{ai_reply}

---

## Instructions
- **APPROVE:** Move to `/Approved/` — WhatsApp Watcher will auto-send it
- **EDIT:** Edit Reply Content above, then move to `/Approved/`
- **REJECT:** Move to `/Rejected/`
""", encoding="utf-8")

    logger.info(f"AI reply draft created: {filename}")
    _log("REPLY_DRAFTED", f"{msg['contact']} -> {filename}")


# ── Sender ────────────────────────────────────────────────────────────────────

def send_reply(contact: str, message: str) -> dict:
    """Send a WhatsApp message to a contact."""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would send to {contact}: {message[:60]}")
        return {"status": "dry_run", "message": "DRY RUN — not sent"}

    if not BROWSER_DIR.exists():
        return {"status": "error", "message": "No session. Run --setup"}

    debug_dir = Path("debug_screenshots")
    debug_dir.mkdir(exist_ok=True)

    try:
        with sync_playwright() as p:
            context = _launch(p, headless=False)
            page = context.new_page()
            logger.info("Opening WhatsApp Web for sending...")
            page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            if not _wait_for_home(page, timeout_sec=60):
                context.close()
                return {"status": "error", "message": "Session expired. Run --setup"}

            time.sleep(2)

            # Find contact in chat list by exact name match
            chat_opened = False
            chats = page.query_selector_all("#pane-side [tabindex='-1']")
            for chat in chats:
                try:
                    name_el = chat.query_selector("span[title], [data-testid='cell-frame-title']")
                    if name_el:
                        name = name_el.get_attribute("title") or name_el.inner_text()
                        if name.strip().lower() == contact.strip().lower():
                            chat.click()
                            time.sleep(3)
                            chat_opened = True
                            logger.info(f"Opened chat via list: {contact}")
                            break
                except Exception:
                    continue

            # Fallback: use search bar if not found in list
            if not chat_opened:
                logger.info(f"'{contact}' not in visible list, trying search...")
                search = None
                for s_sel in [
                    "[data-testid='chat-list-search']",
                    "[aria-label='Search input textbox']",
                    "[aria-label='Search or start new chat']",
                    "div[contenteditable='true'][data-tab='3']",
                    "#side div[contenteditable='true']",
                ]:
                    try:
                        search = page.wait_for_selector(s_sel, timeout=5000)
                        if search and search.is_visible():
                            break
                    except Exception:
                        continue
                if not search:
                    context.close()
                    return {"status": "error", "message": "Could not find search box or contact"}
                search.click()
                time.sleep(1)
                page.keyboard.type(contact, delay=80)
                time.sleep(3)
                page.screenshot(path=str(debug_dir / "wa_2_search.png"))

                # Find exact match in search results
                time.sleep(1)
                results = page.query_selector_all("[data-testid='cell-frame-container']")
                clicked = False
                for r in results:
                    try:
                        name_el = r.query_selector("span[title], [data-testid='cell-frame-title']")
                        if name_el:
                            name = name_el.get_attribute("title") or name_el.inner_text()
                            if contact.strip().lower() in name.strip().lower():
                                r.click()
                                time.sleep(3)
                                clicked = True
                                logger.info(f"Opened chat via search: {name}")
                                break
                    except Exception:
                        continue
                if not clicked:
                    context.close()
                    return {"status": "error", "message": f"Contact '{contact}' not found in WhatsApp"}

            page.screenshot(path=str(debug_dir / "wa_3_chat.png"))

            page.screenshot(path=str(debug_dir / "wa_3b_chat_open.png"))

            # Type message — try multiple selectors
            msg_input = None
            for sel in [
                "[data-testid='conversation-compose-box-input']",
                "div[contenteditable='true'][data-tab='10']",
                "[aria-label='Type a message'][contenteditable='true']",
                "footer div[contenteditable='true']",
                "div[contenteditable='true']",
            ]:
                try:
                    el = page.wait_for_selector(sel, timeout=5000)
                    if el and el.is_visible():
                        msg_input = el
                        logger.info(f"Found message input: {sel}")
                        break
                except Exception:
                    continue

            if not msg_input:
                page.screenshot(path=str(debug_dir / "wa_error_no_input.png"))
                raise RuntimeError("Could not find message input box")
            msg_input.click()
            time.sleep(1)

            for line in message.split("\n"):
                page.keyboard.type(line, delay=30)
                page.keyboard.press("Shift+Enter")
            time.sleep(1)

            page.screenshot(path=str(debug_dir / "wa_4_typed.png"))

            # Send
            send = page.wait_for_selector(
                "[data-testid='send'], [aria-label='Send']",
                timeout=5000,
            )
            send.click()
            time.sleep(3)

            page.screenshot(path=str(debug_dir / "wa_5_sent.png"))
            logger.info(f"Message sent to {contact}!")
            context.close()
            return {"status": "success", "message": f"Sent to {contact}"}

    except Exception as e:
        logger.error(f"Send failed: {e}")
        _log("SEND_ERROR", str(e)[:200])
        return {"status": "error", "message": str(e)[:200]}


def send_approved_replies() -> list:
    """Send all approved WHATSAPP_REPLY_*.md files."""
    files = list(APPROVED_DIR.glob("WHATSAPP_REPLY_*.md"))
    results = []
    for filepath in files:
        contact, message = extract_reply(filepath)
        if not contact or not message:
            logger.warning(f"Skipping {filepath.name} — missing contact or message")
            continue
        result = send_reply(contact, message)
        results.append({"file": filepath, "result": result})
        if result["status"] in ("success", "dry_run"):
            raw = filepath.read_text(encoding="utf-8")
            raw = raw.replace("status: pending_approval", "status: sent")
            raw += f"\n\n## Sent [{datetime.now(timezone.utc).isoformat()}]\n- **Result:** {result['message']}\n"
            (DONE_DIR / filepath.name).write_text(raw, encoding="utf-8")
            filepath.unlink()
            _log("REPLY_SENT", filepath.name)
    return results


# ── Watcher ───────────────────────────────────────────────────────────────────

class WhatsAppWatcher(BaseWatcher):
    def __init__(self, vault_path: str, check_interval: int = 60):
        super().__init__(vault_path, check_interval=check_interval)

    def check_for_updates(self) -> list:
        return check_messages()

    def create_action_file(self, item: dict) -> Path:
        return save_to_inbox(item)

    def run(self):
        """Persistent headless browser — stays open, checks every 30s, instant on new message."""
        logger.info("WhatsApp Watcher started (headless background mode).")
        stop_file = VAULT_PATH / "STOP.md"

        while True:
            if stop_file.exists():
                logger.warning("STOP.md found — paused.")
                time.sleep(10)
                continue
            try:
                logger.info("Starting persistent headless browser session...")
                self._run_persistent()
            except KeyboardInterrupt:
                logger.info("Stopped.")
                break
            except Exception as e:
                logger.error(f"Session error: {e} — restarting in 30s...")
                self.log_event("ERROR", str(e))
                time.sleep(30)

    def _run_persistent(self):
        """Keep browser open continuously. Check for unread every 30s. No browser popup."""
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed.")
            return
        if not BROWSER_DIR.exists():
            logger.error("No session. Run: python watchers/whatsapp_watcher.py --setup")
            return

        seen_file = VAULT_PATH / ".processed_whatsapp_ids"
        seen_ids = set(seen_file.read_text(encoding="utf-8").splitlines()) if seen_file.exists() else set()

        with sync_playwright() as p:
            # headless=True — no browser window on screen
            context = _launch(p, headless=True)
            page = context.new_page()
            logger.info("Opening WhatsApp Web (background, headless)...")
            page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(8)

            if not _wait_for_home(page, timeout_sec=90):
                logger.error("WhatsApp home not loaded. Run --setup again (with visible browser).")
                context.close()
                return

            logger.info("WhatsApp connected. Watching for new messages...")
            stop_file = VAULT_PATH / "STOP.md"

            while True:
                if stop_file.exists():
                    logger.warning("STOP.md — pausing.")
                    time.sleep(10)
                    continue

                try:
                    # ── Check for unread badges ───────────────────────────
                    has_unread = page.evaluate("""() => {
                        const badges = document.querySelectorAll(
                            '[data-testid="icon-unread-count"], span[aria-label*="unread"], span[data-testid="badge"]'
                        );
                        return badges.length > 0;
                    }""")

                    if has_unread:
                        logger.info("Unread message detected! Processing...")
                        chats = page.query_selector_all("#pane-side [tabindex='-1']")
                        for chat in chats:
                            try:
                                badge = None
                                for badge_sel in ["[data-testid='icon-unread-count']", "span[aria-label*='unread']"]:
                                    badge = chat.query_selector(badge_sel)
                                    if badge:
                                        break
                                if not badge:
                                    continue

                                name_el = None
                                for name_sel in ["[data-testid='cell-frame-title']", "span[title]", "span[dir='auto']"]:
                                    name_el = chat.query_selector(name_sel)
                                    if name_el:
                                        break
                                contact = name_el.inner_text().strip() if name_el else "Unknown"

                                chat_id = f"wa_{_safe_name(contact)}_{datetime.now().strftime('%Y%m%d')}"
                                if chat_id in seen_ids:
                                    continue

                                chat.click()
                                time.sleep(2)

                                chat_texts = page.evaluate("""() => {
                                    const texts = [];
                                    const rows = document.querySelectorAll('[data-testid="msg-container"]');
                                    const last = Array.from(rows).slice(-10);
                                    for (const row of last) {
                                        const copyable = row.querySelector('.copyable-text');
                                        if (copyable) {
                                            const spans = copyable.querySelectorAll('span');
                                            let txt = '';
                                            for (const s of spans) {
                                                if (s.children.length === 0 && s.textContent.trim())
                                                    txt += s.textContent.trim() + ' ';
                                            }
                                            txt = txt.trim();
                                            if (txt.length > 1) { texts.push(txt); continue; }
                                            txt = copyable.innerText.trim();
                                            if (txt) { texts.push(txt); continue; }
                                        }
                                        const full = row.innerText.trim();
                                        if (full && full.length > 2) texts.push(full.slice(0, 400));
                                    }
                                    return texts;
                                }""") or []

                                msg = {"contact": contact, "messages": chat_texts, "chat_id": chat_id}
                                p_path = save_to_inbox(msg)
                                seen_ids.add(chat_id)
                                seen_file.write_text("\n".join(seen_ids), encoding="utf-8")
                                self.log_event("WA_SAVED", p_path.name)
                                logger.info(f"Saved + drafted reply for: {contact}")

                                # Go back to main chat list
                                page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=30000)
                                time.sleep(3)
                                _wait_for_home(page, timeout_sec=20)

                            except Exception as e:
                                logger.warning(f"Chat error: {e}")
                                continue

                    # ── Send approved replies ─────────────────────────────
                    approved_files = list(APPROVED_DIR.glob("WHATSAPP_REPLY_*.md"))
                    for filepath in approved_files:
                        contact, message = extract_reply(filepath)
                        if not contact or not message:
                            continue
                        try:
                            page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=30000)
                            time.sleep(3)
                            _wait_for_home(page, timeout_sec=20)

                            chats2 = page.query_selector_all("#pane-side [tabindex='-1']")
                            opened = False
                            for ch in chats2:
                                try:
                                    name_el = ch.query_selector("span[title], [data-testid='cell-frame-title']")
                                    if name_el:
                                        name = name_el.get_attribute("title") or name_el.inner_text()
                                        if name.strip().lower() == contact.strip().lower():
                                            ch.click()
                                            time.sleep(3)
                                            opened = True
                                            break
                                except Exception:
                                    continue

                            if not opened:
                                logger.warning(f"Contact '{contact}' not found")
                                continue

                            msg_input = None
                            for sel in ["div[contenteditable='true'][data-tab='10']", "[data-testid='conversation-compose-box-input']", "footer div[contenteditable='true']"]:
                                try:
                                    el = page.wait_for_selector(sel, timeout=5000)
                                    if el and el.is_visible():
                                        msg_input = el
                                        break
                                except Exception:
                                    continue

                            if not msg_input:
                                continue

                            msg_input.click()
                            time.sleep(1)
                            for line in message.split("\n"):
                                page.keyboard.type(line, delay=30)
                                page.keyboard.press("Shift+Enter")
                            time.sleep(1)

                            send_btn = page.wait_for_selector("[data-testid='send'], [aria-label='Send']", timeout=5000)
                            send_btn.click()
                            time.sleep(3)

                            logger.info(f"Reply sent to {contact}!")
                            raw = filepath.read_text(encoding="utf-8")
                            raw = raw.replace("status: pending_approval", "status: sent")
                            raw += f"\n\n## Sent [{datetime.now(timezone.utc).isoformat()}]\n"
                            (DONE_DIR / filepath.name).write_text(raw, encoding="utf-8")
                            filepath.unlink()
                            self.log_event("WA_SENT", filepath.name)
                            _log("REPLY_SENT", filepath.name)

                        except Exception as e:
                            logger.error(f"Send failed for {contact}: {e}")

                except Exception as e:
                    logger.warning(f"Cycle error: {e}")

                time.sleep(30)  # Check every 30 seconds — lightweight, no browser open/close

    def _run_cycle(self):
        """One cycle: open browser once, check messages + send replies, close."""
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not installed.")
            return
        if not BROWSER_DIR.exists():
            logger.error("No session. Run: python watchers/whatsapp_watcher.py --setup")
            return

        seen_file = VAULT_PATH / ".processed_whatsapp_ids"
        seen_ids = set(seen_file.read_text(encoding="utf-8").splitlines()) if seen_file.exists() else set()
        approved_files = list(APPROVED_DIR.glob("WHATSAPP_REPLY_*.md"))

        # Skip opening browser if nothing to do
        if not approved_files:
            # Still need to check for new messages
            pass

        stop_file = VAULT_PATH / "STOP.md"
        debug_dir = Path("debug_screenshots")
        debug_dir.mkdir(exist_ok=True)

        try:
            with sync_playwright() as p:
                context = _launch(p, headless=False)
                page = context.new_page()
                logger.info("Opening WhatsApp Web...")
                page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=60000)
                time.sleep(5)

                if not _wait_for_home(page, timeout_sec=60):
                    logger.error("WhatsApp home not loaded. Run --setup again.")
                    context.close()
                    return

                time.sleep(2)

                # ── 1. Check for new messages ─────────────────────────────
                logger.info("Scanning for unread chats...")
                chats = []
                for sel in [
                    "[data-testid='cell-frame-container']",
                    "div[role='listitem']",
                    "#pane-side [tabindex='-1']",
                    "#pane-side > div > div > div > div",
                ]:
                    chats = page.query_selector_all(sel)
                    if chats:
                        break

                new_msgs = []
                for chat in chats:
                    try:
                        badge = None
                        for badge_sel in ["[data-testid='icon-unread-count']", "span[aria-label*='unread']", "span.bg-icon-unread-count"]:
                            badge = chat.query_selector(badge_sel)
                            if badge:
                                break
                        if not badge:
                            continue

                        name_el = None
                        for name_sel in ["[data-testid='cell-frame-title']", "span[title]", "span[dir='auto']"]:
                            name_el = chat.query_selector(name_sel)
                            if name_el:
                                break
                        contact = name_el.inner_text().strip() if name_el else "Unknown"

                        chat_id = f"wa_{_safe_name(contact)}_{datetime.now().strftime('%Y%m%d')}"
                        if chat_id in seen_ids:
                            continue

                        chat.click()
                        time.sleep(2)

                        # Extract messages via JS
                        chat_texts = page.evaluate("""() => {
                            const texts = [];
                            const allRows = document.querySelectorAll('[data-testid="msg-container"]');
                            const last = Array.from(allRows).slice(-10);
                            for (const row of last) {
                                const copyable = row.querySelector('.copyable-text');
                                if (copyable) {
                                    const spans = copyable.querySelectorAll('span');
                                    let txt = '';
                                    for (const s of spans) {
                                        if (s.children.length === 0 && s.textContent.trim()) {
                                            txt += s.textContent.trim() + ' ';
                                        }
                                    }
                                    txt = txt.trim();
                                    if (txt && txt.length > 1) { texts.push(txt); continue; }
                                    txt = copyable.innerText.trim();
                                    if (txt) { texts.push(txt); continue; }
                                }
                                const full = row.innerText.trim();
                                if (full && full.length > 2) texts.push(full.slice(0, 400));
                            }
                            return texts;
                        }""") or []

                        new_msgs.append({"contact": contact, "messages": chat_texts, "chat_id": chat_id})
                        seen_ids.add(chat_id)
                        logger.info(f"New message from: {contact} — {len(chat_texts)} line(s)")

                    except Exception as e:
                        logger.warning(f"Chat read error: {e}")
                        continue

                # Save new messages to Inbox + draft replies
                for m in new_msgs:
                    p_path = save_to_inbox(m)
                    self.log_event("WA_SAVED", p_path.name)

                # ── 2. Send approved replies (same browser session) ───────
                approved_files = list(APPROVED_DIR.glob("WHATSAPP_REPLY_*.md"))
                if approved_files:
                    logger.info(f"Sending {len(approved_files)} approved reply/replies...")
                    for filepath in approved_files:
                        contact, message = extract_reply(filepath)
                        if not contact or not message:
                            continue
                        try:
                            # Find contact in chat list
                            sent_ok = False
                            # Go back to main view first
                            page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=30000)
                            time.sleep(3)
                            _wait_for_home(page, timeout_sec=30)

                            chats2 = page.query_selector_all("#pane-side [tabindex='-1']")
                            for ch in chats2:
                                try:
                                    name_el = ch.query_selector("span[title], [data-testid='cell-frame-title']")
                                    if name_el:
                                        name = name_el.get_attribute("title") or name_el.inner_text()
                                        if name.strip().lower() == contact.strip().lower():
                                            ch.click()
                                            time.sleep(3)
                                            sent_ok = True
                                            break
                                except Exception:
                                    continue

                            if not sent_ok:
                                logger.warning(f"Contact '{contact}' not found in chat list")
                                continue

                            # Find message input and send
                            msg_input = None
                            for sel in [
                                "div[contenteditable='true'][data-tab='10']",
                                "[data-testid='conversation-compose-box-input']",
                                "[aria-label='Type a message'][contenteditable='true']",
                                "footer div[contenteditable='true']",
                            ]:
                                try:
                                    el = page.wait_for_selector(sel, timeout=5000)
                                    if el and el.is_visible():
                                        msg_input = el
                                        break
                                except Exception:
                                    continue

                            if not msg_input:
                                logger.warning(f"Message input not found for {contact}")
                                continue

                            msg_input.click()
                            time.sleep(1)
                            for line in message.split("\n"):
                                page.keyboard.type(line, delay=30)
                                page.keyboard.press("Shift+Enter")
                            time.sleep(1)

                            send_btn = page.wait_for_selector("[data-testid='send'], [aria-label='Send']", timeout=5000)
                            send_btn.click()
                            time.sleep(3)

                            logger.info(f"Sent to {contact}!")
                            raw = filepath.read_text(encoding="utf-8")
                            raw = raw.replace("status: pending_approval", "status: sent")
                            raw += f"\n\n## Sent [{datetime.now(timezone.utc).isoformat()}]\n"
                            (DONE_DIR / filepath.name).write_text(raw, encoding="utf-8")
                            filepath.unlink()
                            self.log_event("WA_SENT", filepath.name)
                            _log("REPLY_SENT", filepath.name)

                        except Exception as e:
                            logger.error(f"Send failed for {contact}: {e}")

                context.close()
                seen_file.write_text("\n".join(seen_ids), encoding="utf-8")
                logger.info(f"Cycle done. New: {len(new_msgs)}, Sent: {len(approved_files)}")

        except Exception as e:
            logger.error(f"Cycle error: {e}")
            _log("CYCLE_ERROR", str(e)[:200])


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI Employee — WhatsApp Watcher")
    parser.add_argument("--vault",      default=os.getenv("VAULT_PATH", "AI_Employee_Vault"))
    parser.add_argument("--interval",   type=int, default=60)
    parser.add_argument("--setup",      action="store_true")
    parser.add_argument("--check-now",  action="store_true")
    parser.add_argument("--send-now",   action="store_true")
    parser.add_argument("--dry-run",    action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
        global DRY_RUN
        DRY_RUN = True

    if args.setup:
        setup_session()
        return

    watcher = WhatsAppWatcher(vault_path=args.vault, check_interval=args.interval)

    if args.check_now:
        msgs = check_messages()
        logger.info(f"Found {len(msgs)} new message(s)")
        for m in msgs:
            save_to_inbox(m)
        logger.info("Done.")
    elif args.send_now:
        results = send_approved_replies()
        logger.info(f"Sent {len(results)} reply/replies.")
    else:
        watcher.run()


if __name__ == "__main__":
    main()
