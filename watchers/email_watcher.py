"""
email_watcher.py — Email Auto-Sender for AI Employee (Silver Tier)

Watches /Approved/ folder for DRAFT_EMAIL_*.md files and sends them via SMTP.

Workflow:
  1. Claude drafts an email → saves DRAFT_EMAIL_*.md to /Drafts/
  2. Human reviews → moves file to /Approved/
  3. This watcher detects it → sends the email → moves to /Done/

Usage:
    python watchers/email_watcher.py          # Watch mode
    python watchers/email_watcher.py --send-now  # Send all approved immediately
    python watchers/email_watcher.py --dry-run   # Test without sending
"""

import os
import sys
import re
import time
import smtplib
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EmailWatcher] %(levelname)s: %(message)s",
)
logger = logging.getLogger("EmailWatcher")

# ── Config ──────────────────────────────────────────────────────────────────────
EMAIL_FROM   = os.getenv("EMAIL_FROM", "")
APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")
SMTP_HOST    = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
VAULT_PATH   = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
DRY_RUN      = os.getenv("DRY_RUN", "false").lower() == "true"

APPROVED_DIR = VAULT_PATH / "Approved"
DONE_DIR     = VAULT_PATH / "Done"
LOGS_DIR     = VAULT_PATH / "Logs"


# ── Draft parser ────────────────────────────────────────────────────────────────

def parse_draft(filepath: Path) -> dict:
    """Parse a DRAFT_EMAIL_*.md file and extract to, subject, body."""
    content = filepath.read_text(encoding="utf-8")

    # Extract frontmatter fields
    to_match      = re.search(r"^to:\s*(.+)$",      content, re.MULTILINE)
    subject_match = re.search(r"^subject:\s*(.+)$",  content, re.MULTILINE)
    cc_match      = re.search(r"^cc:\s*(.+)$",       content, re.MULTILINE)

    to      = to_match.group(1).strip()      if to_match      else ""
    subject = subject_match.group(1).strip() if subject_match else "(No Subject)"
    cc      = cc_match.group(1).strip()      if cc_match      else ""

    # Extract body — everything between the two --- dividers after the header table
    body_match = re.search(r"---\s*\n\n(.+?)\n\n---", content, re.DOTALL)
    body = body_match.group(1).strip() if body_match else ""

    # Fallback: everything after last ---
    if not body:
        parts = content.split("---")
        if len(parts) >= 3:
            body = parts[-2].strip()

    return {"to": to, "subject": subject, "cc": cc, "body": body}


# ── Email Sender ────────────────────────────────────────────────────────────────

class EmailSender:
    """Sends emails via SMTP."""

    def _log(self, action: str, details: str):
        today = datetime.now().strftime("%Y-%m-%d")
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        entry = f"[{datetime.now(timezone.utc).isoformat()}] [EmailSender] {action}: {details}\n"
        with open(LOGS_DIR / f"{today}.log", "a", encoding="utf-8") as f:
            f.write(entry)

    def send(self, to: str, subject: str, body: str, cc: str = "") -> dict:
        """Send an email via Gmail SMTP."""
        if not to:
            return {"status": "error", "message": "No recipient (to:) found in draft"}

        if DRY_RUN:
            logger.info(f"[DRY RUN] Would send email to: {to} | Subject: {subject}")
            self._log("SEND_DRY_RUN", f"to={to} subject={subject}")
            return {"status": "dry_run", "message": f"DRY RUN — would send to {to}"}

        if not EMAIL_FROM or not APP_PASSWORD:
            return {"status": "error", "message": "EMAIL_FROM and EMAIL_APP_PASSWORD not set in .env"}

        msg = MIMEMultipart()
        msg["From"]    = EMAIL_FROM
        msg["To"]      = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        msg.attach(MIMEText(body, "plain", "utf-8"))

        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.login(EMAIL_FROM, APP_PASSWORD)
                recipients = [to] + ([cc] if cc else [])
                server.sendmail(EMAIL_FROM, recipients, msg.as_string())

            logger.info(f"Email sent to {to} | Subject: {subject}")
            self._log("SEND_SUCCESS", f"to={to} subject={subject}")
            return {"status": "success", "message": f"Email sent to {to}"}

        except smtplib.SMTPAuthenticationError:
            msg = "Gmail authentication failed — check EMAIL_APP_PASSWORD in .env"
            logger.error(msg)
            self._log("SEND_ERROR", msg)
            return {"status": "error", "message": msg}

        except Exception as e:
            logger.error(f"Send failed: {e}")
            self._log("SEND_ERROR", str(e)[:200])
            return {"status": "error", "message": str(e)[:200]}


# ── Watcher ─────────────────────────────────────────────────────────────────────

class EmailWatcher(BaseWatcher):
    """Watches /Approved/ for DRAFT_EMAIL_*.md files and sends them."""

    def __init__(self, vault_path: str, check_interval: int = 30):
        super().__init__(vault_path, check_interval=check_interval)
        self.approved_dir = VAULT_PATH / "Approved"
        self.done_dir     = VAULT_PATH / "Done"
        self.sender       = EmailSender()
        self._sent: set   = set()

    def check_for_updates(self) -> list:
        return [
            f for f in self.approved_dir.glob("DRAFT_EMAIL_*.md")
            if str(f) not in self._sent
        ]

    def create_action_file(self, item: Path) -> Path:
        draft = parse_draft(item)

        if not draft["to"]:
            logger.warning(f"No recipient in {item.name} — skipping")
            self._sent.add(str(item))
            return item

        logger.info(f"Sending: {item.name}")
        logger.info(f"To: {draft['to']} | Subject: {draft['subject']}")

        result = self.sender.send(
            to=draft["to"],
            subject=draft["subject"],
            body=draft["body"],
            cc=draft["cc"],
        )

        if result["status"] in ("success", "dry_run"):
            raw = item.read_text(encoding="utf-8")
            raw = raw.replace("status: draft", "status: sent")
            raw += f"\n\n## Sent [{datetime.now(timezone.utc).isoformat()}]\n- **Result:** {result['message']}\n"

            done_path = self.done_dir / item.name
            done_path.write_text(raw, encoding="utf-8")
            item.unlink()

            logger.info(f"Moved to Done: {item.name}")
            self.log_event("EMAIL_SENT", item.name)
            self._update_dashboard(item.name, result["status"])
        else:
            logger.error(f"Send failed: {result['message']}")
            self.log_event("EMAIL_ERROR", result["message"])

        self._sent.add(str(item))
        return item

    def _update_dashboard(self, filename: str, status: str):
        dashboard = VAULT_PATH / "Dashboard.md"
        if not dashboard.exists():
            return
        dash = dashboard.read_text(encoding="utf-8")
        row = f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Email {status}: {filename} |"
        dash = dash.replace(
            "| Time (UTC)          | Action                                      |",
            "| Time (UTC)          | Action                                      |\n" + row
        )
        dashboard.write_text(dash, encoding="utf-8")


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI Employee — Email Watcher")
    parser.add_argument("--vault",     default=os.getenv("VAULT_PATH", "AI_Employee_Vault"))
    parser.add_argument("--interval",  type=int, default=30)
    parser.add_argument("--send-now",  action="store_true")
    parser.add_argument("--dry-run",   action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
        global DRY_RUN
        DRY_RUN = True

    watcher = EmailWatcher(vault_path=args.vault, check_interval=args.interval)

    if args.send_now:
        items = watcher.check_for_updates()
        logger.info(f"Found {len(items)} approved draft(s)")
        for item in items:
            watcher.create_action_file(item)
        logger.info("Done.")
    else:
        watcher.run()


if __name__ == "__main__":
    main()
