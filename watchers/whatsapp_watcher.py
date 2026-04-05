"""
whatsapp_watcher.py — WhatsApp Monitor & Auto-Sender for AI Employee (Gold Tier)

Uses Selenium (ChromeDriver) with persistent user-data-dir on WhatsApp Web.
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
# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException, WebDriverException
    )
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WhatsAppWatcher] %(levelname)s: %(message)s",
)
logger = logging.getLogger("WhatsAppWatcher")

# ── Config ────────────────────────────────────────────────────────────────────
VAULT_PATH    = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
SESSION_PATH  = Path(os.getenv("WHATSAPP_SESSION_PATH", "credentials/whatsapp_session"))
BROWSER_DIR   = Path("D:/AI-Employee/credentials/whatsapp_session/browser_data")
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


def _build_driver(hide_window: bool = False) -> "webdriver.Chrome":
    """Build a Selenium Chrome driver with persistent session."""
    BROWSER_DIR.mkdir(parents=True, exist_ok=True)

    # Remove stale lockfiles left by crashed processes
    for lf in ["lockfile", "SingletonLock", "SingletonCookie"]:
        lock_path = BROWSER_DIR / lf
        if lock_path.exists():
            try:
                lock_path.unlink()
            except Exception:
                pass

    opts = Options()
    opts.add_argument(f"--user-data-dir={BROWSER_DIR}")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--lang=en-US")
    opts.add_argument("--window-size=1280,900")
    if hide_window:
        opts.add_argument("--window-position=-9000,-9000")
    else:
        opts.add_argument("--window-position=100,100")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)

    # Hide webdriver fingerprint
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def _wait_for_home(driver, timeout_sec: int = 90) -> bool:
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
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els and els[0].is_displayed():
                    logger.info(f"WhatsApp home loaded ({sel})")
                    return True
            except Exception:
                pass
        time.sleep(2)
    return False


def _find_element(driver, selectors: list, timeout: int = 5):
    """Try multiple CSS selectors, return first visible element found or None."""
    for sel in selectors:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, sel))
            )
            if el:
                return el
        except Exception:
            pass
    return None


def _screenshot(driver, path: str):
    """Save a screenshot, swallowing errors."""
    try:
        driver.save_screenshot(path)
    except Exception:
        pass


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
    """Open WhatsApp Web for QR scan using Selenium (visible browser)."""
    if not SELENIUM_AVAILABLE:
        print("ERROR: Selenium not installed.")
        print("Run: pip install selenium webdriver-manager")
        return False

    print("\n" + "=" * 55)
    print("WHATSAPP WEB SESSION SETUP")
    print("=" * 55)
    print("Browser will open — scan QR code with your phone.")
    print("=" * 55 + "\n")

    try:
        driver = _build_driver(hide_window=False)
        print("Opening https://web.whatsapp.com ...")
        driver.get(WHATSAPP_URL)
        time.sleep(5)

        print("Scan the QR code in the browser window...")
        loaded = _wait_for_home(driver, timeout_sec=120)
        if loaded:
            print("WhatsApp home loaded! Session saved.")
        else:
            print("Timeout — session may still be saved.")

        input("\nPress Enter to save session and close: ")
        driver.quit()
        print(f"\nDone! Session: {BROWSER_DIR}")
        _log("SETUP_COMPLETE", str(BROWSER_DIR))
        return True

    except Exception as e:
        print(f"\nERROR: {e}")
        return False


# ── Message Checker ───────────────────────────────────────────────────────────

def check_messages() -> list:
    """Open WhatsApp Web, find unread chats, return list of message dicts."""
    if not SELENIUM_AVAILABLE:
        logger.error("Selenium not installed.")
        return []

    if not BROWSER_DIR.exists():
        logger.error("No session found. Run: python watchers/whatsapp_watcher.py --setup")
        return []

    messages = []
    seen_file = VAULT_PATH / ".processed_whatsapp_ids"
    seen_ids = set(seen_file.read_text(encoding="utf-8").splitlines()) if seen_file.exists() else set()

    debug_dir = Path("debug_screenshots")
    debug_dir.mkdir(exist_ok=True)

    driver = None
    try:
        driver = _build_driver(hide_window=False)
        logger.info("Opening WhatsApp Web (visible for setup)...")
        driver.get(WHATSAPP_URL)
        time.sleep(5)

        loaded = _wait_for_home(driver, timeout_sec=60)
        if not loaded:
            _screenshot(driver, str(debug_dir / "wa_error_login.png"))
            logger.error("WhatsApp home not loaded. Run --setup again.")
            driver.quit()
            return []

        time.sleep(2)
        _screenshot(driver, str(debug_dir / "wa_1_home.png"))
        logger.info("Scanning for unread chats...")

        # Find chats with unread badge — try multiple selectors
        chats = []
        for sel in [
            "[data-testid='cell-frame-container']",
            "div[role='listitem']",
            "#pane-side [tabindex='-1']",
            "#pane-side > div > div > div > div",
        ]:
            chats = driver.find_elements(By.CSS_SELECTOR, sel)
            if chats:
                logger.info(f"Found {len(chats)} chats with: {sel}")
                break
        logger.info(f"Chats visible: {len(chats)}")

        for chat in chats:
            try:
                # Check for unread badge using JS (WhatsApp uses obfuscated class names)
                has_badge = driver.execute_script("""
                    const chat = arguments[0];
                    // Look for a span containing only digits (unread count)
                    const spans = chat.querySelectorAll('span');
                    for (const s of spans) {
                        const t = s.textContent.trim();
                        if (/^[0-9]+$/.test(t) && parseInt(t) > 0 && parseInt(t) < 1000) {
                            // Make sure it looks like a badge (small, positioned)
                            const r = s.getBoundingClientRect();
                            if (r.width > 0 && r.width < 40) return true;
                        }
                    }
                    // Also check aria-label on the chat row
                    const label = chat.getAttribute('aria-label') || '';
                    if (label.toLowerCase().includes('unread')) return true;
                    return false;
                """, chat)
                if not has_badge:
                    continue

                # Get contact name
                name_el = None
                for name_sel in [
                    "[data-testid='cell-frame-title']",
                    "span[title]",
                    "span[dir='auto']",
                ]:
                    found = chat.find_elements(By.CSS_SELECTOR, name_sel)
                    if found:
                        name_el = found[0]
                        break
                contact = name_el.text.strip() if name_el else "Unknown"

                chat_id = f"wa_{_safe_name(contact)}_{datetime.now().strftime('%Y%m%d_%H')}"
                if chat_id in seen_ids:
                    continue

                chat.click()
                time.sleep(3)

                # Extract incoming messages using JavaScript (most reliable)
                chat_texts = driver.execute_script("""
                    const texts = [];
                    const incomingRows = document.querySelectorAll(
                        '[data-testid="msg-container"]:not(.message-out), ' +
                        '.message-in [data-testid="msg-container"], ' +
                        'div[class*="message-in"]'
                    );
                    const allRows = document.querySelectorAll('[data-testid="msg-container"]');
                    const rows = incomingRows.length > 0 ? incomingRows : allRows;
                    const last = Array.from(rows).slice(-10);
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
                """)
                if not chat_texts:
                    chat_texts = []

                messages.append({"contact": contact, "messages": chat_texts, "chat_id": chat_id})
                seen_ids.add(chat_id)
                logger.info(f"New message from: {contact}")

            except Exception as e:
                logger.warning(f"Chat read error: {e}")
                continue

        driver.quit()
        seen_file.write_text("\n".join(seen_ids), encoding="utf-8")

    except Exception as e:
        logger.error(f"check_messages failed: {e}")
        _log("CHECK_ERROR", str(e)[:200])
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

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

def _open_chat_in_driver(driver, contact: str, debug_dir: Path) -> bool:
    """Find and click a chat by contact name. Returns True if opened."""
    # Try chat list first
    chats = driver.find_elements(By.CSS_SELECTOR, "#pane-side [tabindex='-1']")
    for chat in chats:
        try:
            name_els = chat.find_elements(By.CSS_SELECTOR, "span[title], [data-testid='cell-frame-title']")
            if name_els:
                name = name_els[0].get_attribute("title") or name_els[0].text
                if name.strip().lower() == contact.strip().lower():
                    chat.click()
                    time.sleep(3)
                    logger.info(f"Opened chat via list: {contact}")
                    return True
        except Exception:
            continue

    # Fallback: use search bar
    logger.info(f"'{contact}' not in visible list, trying search...")
    search = _find_element(driver, [
        "[data-testid='chat-list-search']",
        "[aria-label='Search input textbox']",
        "[aria-label='Search or start new chat']",
        "div[contenteditable='true'][data-tab='3']",
        "#side div[contenteditable='true']",
    ], timeout=5)

    if not search:
        return False

    search.click()
    time.sleep(1)
    search.send_keys(contact)
    time.sleep(3)
    _screenshot(driver, str(debug_dir / "wa_2_search.png"))

    time.sleep(1)
    results = driver.find_elements(By.CSS_SELECTOR, "[data-testid='cell-frame-container']")
    for r in results:
        try:
            name_els = r.find_elements(By.CSS_SELECTOR, "span[title], [data-testid='cell-frame-title']")
            if name_els:
                name = name_els[0].get_attribute("title") or name_els[0].text
                if contact.strip().lower() in name.strip().lower():
                    r.click()
                    time.sleep(3)
                    logger.info(f"Opened chat via search: {name}")
                    return True
        except Exception:
            continue

    return False


def _type_and_send(driver, message: str):
    """Type message into compose box and send it."""
    msg_input = _find_element(driver, [
        "[data-testid='conversation-compose-box-input']",
        "div[contenteditable='true'][data-tab='10']",
        "[aria-label='Type a message'][contenteditable='true']",
        "footer div[contenteditable='true']",
        "div[contenteditable='true']",
    ], timeout=5)

    if not msg_input:
        raise RuntimeError("Could not find message input box")

    msg_input.click()
    time.sleep(1)

    for line in message.split("\n"):
        msg_input.send_keys(line)
        msg_input.send_keys(Keys.SHIFT, Keys.ENTER)
    time.sleep(1)

    # Send button
    send_btn = _find_element(driver, [
        "[data-testid='send']",
        "[aria-label='Send']",
    ], timeout=5)
    if not send_btn:
        raise RuntimeError("Could not find Send button")
    send_btn.click()
    time.sleep(3)


def send_reply(contact: str, message: str) -> dict:
    """Send a WhatsApp message to a contact."""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would send to {contact}: {message[:60]}")
        return {"status": "dry_run", "message": "DRY RUN — not sent"}

    if not BROWSER_DIR.exists():
        return {"status": "error", "message": "No session. Run --setup"}

    debug_dir = Path("debug_screenshots")
    debug_dir.mkdir(exist_ok=True)

    driver = None
    try:
        driver = _build_driver(hide_window=False)
        logger.info("Opening WhatsApp Web for sending...")
        driver.get(WHATSAPP_URL)
        time.sleep(5)

        if not _wait_for_home(driver, timeout_sec=60):
            driver.quit()
            return {"status": "error", "message": "Session expired. Run --setup"}

        time.sleep(2)

        chat_opened = _open_chat_in_driver(driver, contact, debug_dir)
        if not chat_opened:
            driver.quit()
            return {"status": "error", "message": f"Contact '{contact}' not found in WhatsApp"}

        _screenshot(driver, str(debug_dir / "wa_3_chat.png"))
        _screenshot(driver, str(debug_dir / "wa_3b_chat_open.png"))

        _type_and_send(driver, message)

        _screenshot(driver, str(debug_dir / "wa_4_typed.png"))
        _screenshot(driver, str(debug_dir / "wa_5_sent.png"))
        logger.info(f"Message sent to {contact}!")
        driver.quit()
        return {"status": "success", "message": f"Sent to {contact}"}

    except Exception as e:
        logger.error(f"Send failed: {e}")
        _log("SEND_ERROR", str(e)[:200])
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
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
            DONE_DIR.mkdir(parents=True, exist_ok=True)
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
        """Persistent background browser — stays open, checks every 30s."""
        logger.info("WhatsApp Watcher started (background mode).")
        stop_file = VAULT_PATH / "STOP.md"

        while True:
            if stop_file.exists():
                logger.warning("STOP.md found — paused.")
                time.sleep(10)
                continue
            try:
                logger.info("Starting persistent browser session...")
                self._run_persistent()
            except KeyboardInterrupt:
                logger.info("Stopped.")
                break
            except Exception as e:
                logger.error(f"Session error: {e} — restarting in 30s...")
                self.log_event("ERROR", str(e))
                time.sleep(30)

    def _run_persistent(self):
        """Keep browser open continuously. Check for unread every 30s."""
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not installed.")
            return
        if not BROWSER_DIR.exists():
            logger.error("No session. Run: python watchers/whatsapp_watcher.py --setup")
            return

        seen_file = VAULT_PATH / ".processed_whatsapp_ids"
        seen_ids = set(seen_file.read_text(encoding="utf-8").splitlines()) if seen_file.exists() else set()

        driver = None
        try:
            # hide_window=True moves Chrome off-screen — works with Selenium/ChromeDriver
            driver = _build_driver(hide_window=True)
            logger.info("Opening WhatsApp Web (background, off-screen window)...")
            driver.get(WHATSAPP_URL)
            time.sleep(8)

            if not _wait_for_home(driver, timeout_sec=90):
                logger.error("WhatsApp home not loaded. Run --setup again (with visible browser).")
                driver.quit()
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
                    has_unread = driver.execute_script("""
                        const spans = document.querySelectorAll('#pane-side span');
                        for (const s of spans) {
                            const t = s.textContent.trim();
                            if (/^[0-9]+$/.test(t) && parseInt(t) > 0 && parseInt(t) < 1000) {
                                const r = s.getBoundingClientRect();
                                if (r.width > 0 && r.width < 40) return true;
                            }
                        }
                        return false;
                    """)

                    if has_unread:
                        logger.info("Unread message detected! Processing...")
                        chats = driver.find_elements(By.CSS_SELECTOR, "#pane-side [tabindex='-1']")
                        for chat in chats:
                            try:
                                has_badge = driver.execute_script("""
                                    const chat = arguments[0];
                                    const spans = chat.querySelectorAll('span');
                                    for (const s of spans) {
                                        const t = s.textContent.trim();
                                        if (/^[0-9]+$/.test(t) && parseInt(t) > 0 && parseInt(t) < 1000) {
                                            const r = s.getBoundingClientRect();
                                            if (r.width > 0 && r.width < 40) return true;
                                        }
                                    }
                                    return false;
                                """, chat)
                                if not has_badge:
                                    continue

                                name_el = None
                                for name_sel in [
                                    "[data-testid='cell-frame-title']",
                                    "span[title]",
                                    "span[dir='auto']",
                                ]:
                                    found = chat.find_elements(By.CSS_SELECTOR, name_sel)
                                    if found:
                                        name_el = found[0]
                                        break
                                contact = name_el.text.strip() if name_el else "Unknown"

                                chat_id = f"wa_{_safe_name(contact)}_{datetime.now().strftime('%Y%m%d_%H')}"
                                if chat_id in seen_ids:
                                    continue

                                chat.click()
                                time.sleep(2)

                                chat_texts = driver.execute_script("""
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
                                """) or []

                                msg = {"contact": contact, "messages": chat_texts, "chat_id": chat_id}
                                p_path = save_to_inbox(msg)
                                seen_ids.add(chat_id)
                                seen_file.write_text("\n".join(seen_ids), encoding="utf-8")
                                self.log_event("WA_SAVED", p_path.name)
                                logger.info(f"Saved + drafted reply for: {contact}")

                                # Go back to main chat list
                                driver.get(WHATSAPP_URL)
                                time.sleep(3)
                                _wait_for_home(driver, timeout_sec=20)

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
                            driver.get(WHATSAPP_URL)
                            time.sleep(3)
                            _wait_for_home(driver, timeout_sec=20)

                            chats2 = driver.find_elements(By.CSS_SELECTOR, "#pane-side [tabindex='-1']")
                            opened = False
                            for ch in chats2:
                                try:
                                    name_els = ch.find_elements(By.CSS_SELECTOR, "span[title], [data-testid='cell-frame-title']")
                                    if name_els:
                                        name = name_els[0].get_attribute("title") or name_els[0].text
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

                            _type_and_send(driver, message)

                            logger.info(f"Reply sent to {contact}!")
                            raw = filepath.read_text(encoding="utf-8")
                            raw = raw.replace("status: pending_approval", "status: sent")
                            raw += f"\n\n## Sent [{datetime.now(timezone.utc).isoformat()}]\n"
                            DONE_DIR.mkdir(parents=True, exist_ok=True)
                            (DONE_DIR / filepath.name).write_text(raw, encoding="utf-8")
                            filepath.unlink()
                            self.log_event("WA_SENT", filepath.name)
                            _log("REPLY_SENT", filepath.name)

                        except Exception as e:
                            logger.error(f"Send failed for {contact}: {e}")

                except Exception as e:
                    logger.warning(f"Cycle error: {e}")

                time.sleep(30)  # Check every 30 seconds

        except Exception as e:
            logger.error(f"_run_persistent crashed: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def _run_cycle(self):
        """One cycle: open browser once, check messages + send replies, close."""
        if not SELENIUM_AVAILABLE:
            logger.error("Selenium not installed.")
            return
        if not BROWSER_DIR.exists():
            logger.error("No session. Run: python watchers/whatsapp_watcher.py --setup")
            return

        seen_file = VAULT_PATH / ".processed_whatsapp_ids"
        seen_ids = set(seen_file.read_text(encoding="utf-8").splitlines()) if seen_file.exists() else set()

        stop_file = VAULT_PATH / "STOP.md"
        debug_dir = Path("debug_screenshots")
        debug_dir.mkdir(exist_ok=True)

        driver = None
        try:
            driver = _build_driver(hide_window=False)
            logger.info("Opening WhatsApp Web...")
            driver.get(WHATSAPP_URL)
            time.sleep(5)

            if not _wait_for_home(driver, timeout_sec=60):
                logger.error("WhatsApp home not loaded. Run --setup again.")
                driver.quit()
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
                chats = driver.find_elements(By.CSS_SELECTOR, sel)
                if chats:
                    break

            new_msgs = []
            for chat in chats:
                try:
                    badge = None
                    for badge_sel in [
                        "[data-testid='icon-unread-count']",
                        "span[aria-label*='unread']",
                        "span.bg-icon-unread-count",
                    ]:
                        found = chat.find_elements(By.CSS_SELECTOR, badge_sel)
                        if found:
                            badge = found[0]
                            break
                    if not badge:
                        continue

                    name_el = None
                    for name_sel in [
                        "[data-testid='cell-frame-title']",
                        "span[title]",
                        "span[dir='auto']",
                    ]:
                        found = chat.find_elements(By.CSS_SELECTOR, name_sel)
                        if found:
                            name_el = found[0]
                            break
                    contact = name_el.text.strip() if name_el else "Unknown"

                    chat_id = f"wa_{_safe_name(contact)}_{datetime.now().strftime('%Y%m%d_%H')}"
                    if chat_id in seen_ids:
                        continue

                    chat.click()
                    time.sleep(2)

                    chat_texts = driver.execute_script("""
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
                    """) or []

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
                        driver.get(WHATSAPP_URL)
                        time.sleep(3)
                        _wait_for_home(driver, timeout_sec=30)

                        chats2 = driver.find_elements(By.CSS_SELECTOR, "#pane-side [tabindex='-1']")
                        sent_ok = False
                        for ch in chats2:
                            try:
                                name_els = ch.find_elements(By.CSS_SELECTOR, "span[title], [data-testid='cell-frame-title']")
                                if name_els:
                                    name = name_els[0].get_attribute("title") or name_els[0].text
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

                        _type_and_send(driver, message)

                        logger.info(f"Sent to {contact}!")
                        raw = filepath.read_text(encoding="utf-8")
                        raw = raw.replace("status: pending_approval", "status: sent")
                        raw += f"\n\n## Sent [{datetime.now(timezone.utc).isoformat()}]\n"
                        DONE_DIR.mkdir(parents=True, exist_ok=True)
                        (DONE_DIR / filepath.name).write_text(raw, encoding="utf-8")
                        filepath.unlink()
                        self.log_event("WA_SENT", filepath.name)
                        _log("REPLY_SENT", filepath.name)

                    except Exception as e:
                        logger.error(f"Send failed for {contact}: {e}")

            driver.quit()
            seen_file.write_text("\n".join(seen_ids), encoding="utf-8")
            logger.info(f"Cycle done. New: {len(new_msgs)}, Sent: {len(approved_files)}")

        except Exception as e:
            logger.error(f"Cycle error: {e}")
            _log("CYCLE_ERROR", str(e)[:200])
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI Employee — WhatsApp Watcher")
    parser.add_argument("--vault",       default=os.getenv("VAULT_PATH", "AI_Employee_Vault"))
    parser.add_argument("--interval",    type=int, default=60)
    parser.add_argument("--setup",       action="store_true")
    parser.add_argument("--setup-only",  action="store_true")
    parser.add_argument("--check-now",   action="store_true")
    parser.add_argument("--send-now",    action="store_true")
    parser.add_argument("--dry-run",     action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
        global DRY_RUN
        DRY_RUN = True

    if args.setup or args.setup_only:
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
