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
    context = p.chromium.launch_persistent_context(
        str(BROWSER_DIR),
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
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
    """Open WhatsApp Web for QR scan. Session stored in browser_data/."""
    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright not installed.")
        print("Run: pip install playwright && playwright install chromium")
        return False

    print("\n" + "=" * 55)
    print("WHATSAPP WEB SESSION SETUP")
    print("=" * 55)
    print(f"Browser data: {BROWSER_DIR}")
    print("1. Browser khulega")
    print("2. WhatsApp Web QR code dikhega")
    print("3. Phone: WhatsApp > Settings > Linked Devices > Link a Device")
    print("4. QR scan karo")
    print("5. Home load hone ke baad terminal pe Enter dabao")
    print("=" * 55 + "\n")

    try:
        with sync_playwright() as p:
            context = _launch(p, headless=False)
            page = context.new_page()
            print("Opening https://web.whatsapp.com ...")
            page.goto(WHATSAPP_URL, wait_until="domcontentloaded", timeout=60000)
            print("Browser open hai. QR scan karo...")

            loaded = _wait_for_home(page, timeout_sec=120)
            if loaded:
                print("WhatsApp home loaded! Session save hai.")
            else:
                print("Timeout — but session may still be saved.")

            input("\nEnter dabao session save karne ke liye: ")
            context.close()
            print(f"\nDone! Session saved in: {BROWSER_DIR}")
            _log("SETUP_COMPLETE", str(BROWSER_DIR))
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
            logger.info("Opening WhatsApp Web...")
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

                    # Skip groups — group previews show "~ SenderName:" prefix
                    # Also skip if chat has group icon (multiple people icon)
                    preview_el = chat.query_selector("[data-testid='last-msg-status'] ~ span, span[dir='ltr']")
                    preview_text = preview_el.inner_text().strip() if preview_el else ""
                    is_group = (
                        preview_text.startswith("~") or          # group message prefix
                        re.search(r"^\+?\d{10,}", preview_text) or  # phone number prefix
                        chat.query_selector("[data-testid='group']") is not None
                    )
                    if is_group:
                        logger.info(f"Skipping group: {contact}")
                        continue

                    chat_id = f"wa_{_safe_name(contact)}_{datetime.now().strftime('%Y%m%d')}"
                    if chat_id in seen_ids:
                        continue

                    chat.click()
                    time.sleep(2)

                    msg_els = page.query_selector_all("[data-testid='msg-container']")
                    chat_texts = []
                    for m in msg_els[-10:]:
                        try:
                            t = m.query_selector("[data-testid='msg-text'], .copyable-text span")
                            if t:
                                txt = t.inner_text().strip()
                                if txt:
                                    chat_texts.append(txt)
                        except Exception:
                            pass

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
                    f"You are a helpful personal assistant drafting a WhatsApp reply.\n\n"
                    f"Contact: {contact}\n"
                    f"Their messages:\n{msgs_text}\n\n"
                    f"Write a short, friendly, natural WhatsApp reply (2-4 sentences max). "
                    f"No markdown, no formatting — plain text only. "
                    f"Sound human and conversational."
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

            # Search for contact
            search = page.wait_for_selector(
                "[data-testid='chat-list-search'], [aria-label='Search input textbox']",
                timeout=10000,
            )
            search.click()
            time.sleep(1)
            page.keyboard.type(contact, delay=80)
            time.sleep(2)

            page.screenshot(path=str(debug_dir / "wa_2_search.png"))

            # Click the contact/chat result
            time.sleep(2)
            page.screenshot(path=str(debug_dir / "wa_2b_results.png"))

            # Use keyboard Enter on the first result — most reliable way
            page.keyboard.press("ArrowDown")
            time.sleep(0.5)
            page.keyboard.press("Enter")
            time.sleep(3)

            page.screenshot(path=str(debug_dir / "wa_3_chat_opened.png"))

            # Verify chat opened — right panel should have footer/input
            # If not, try clicking the first visible list item
            main_panel = page.query_selector("#main footer, [data-testid='conversation-panel-body']")
            if not main_panel:
                logger.info("Chat not opened via keyboard, trying mouse click...")
                for sel in [
                    "[data-testid='cell-frame-container']",
                    "div[role='listitem']",
                    "#pane-side span[dir='auto']",
                ]:
                    try:
                        el = page.wait_for_selector(sel, timeout=3000)
                        if el and el.is_visible():
                            el.click()
                            time.sleep(3)
                            break
                    except Exception:
                        continue

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
        logger.info("WhatsApp Watcher started.")
        stop_file = VAULT_PATH / "STOP.md"
        while True:
            if stop_file.exists():
                logger.warning("STOP.md found — paused.")
                time.sleep(10)
                continue
            try:
                msgs = check_messages()
                for m in msgs:
                    p = save_to_inbox(m)
                    self.log_event("WA_SAVED", p.name)
                sent = send_approved_replies()
                for r in sent:
                    self.log_event("WA_SENT", r["file"].name)
            except KeyboardInterrupt:
                logger.info("Stopped.")
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                self.log_event("ERROR", str(e))
            time.sleep(self.check_interval)


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
