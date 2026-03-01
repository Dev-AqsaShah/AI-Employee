"""
gmail_watcher.py — Monitors Gmail for important unread emails and creates
Needs_Action items in the Obsidian vault.

Setup:
  1. Enable Gmail API in Google Cloud Console
  2. Download OAuth credentials as credentials/gmail_credentials.json
  3. Run once interactively to complete OAuth: python watchers/gmail_watcher.py
  4. Token saved to credentials/gmail_token.json for future runs

Usage:
    python watchers/gmail_watcher.py [--vault PATH] [--interval SECONDS] [--dry-run]

Environment variables:
    VAULT_PATH              — path to AI_Employee_Vault
    GMAIL_CREDENTIALS_PATH  — path to gmail_credentials.json
    GMAIL_TOKEN_PATH        — path to gmail_token.json (auto-created)
    DRY_RUN                 — 'true' to log without writing files
"""

import os
import sys
import json
import time
import argparse
import base64
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

# ── Dependency check ───────────────────────────────────────────────────────────
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# Gmail OAuth scopes — read-only is enough for watching
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Email query — unread + important
DEFAULT_QUERY = "is:unread is:important"


class GmailWatcher(BaseWatcher):
    """
    Monitors Gmail for important unread emails.
    Creates Needs_Action .md files for each new email.
    """

    def __init__(
        self,
        vault_path: str,
        credentials_path: str = "credentials/gmail_credentials.json",
        token_path: str = "credentials/gmail_token.json",
        check_interval: int = 120,
        query: str = DEFAULT_QUERY,
    ):
        super().__init__(vault_path, check_interval=check_interval)
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.query = query
        self.service = None
        self._processed_ids_file = self.vault_path / ".processed_gmail_ids"
        self._processed_ids: set = self._load_processed_ids()

    # ── ID persistence ─────────────────────────────────────────────────────────

    def _load_processed_ids(self) -> set:
        if self._processed_ids_file.exists():
            return set(self._processed_ids_file.read_text().splitlines())
        return set()

    def _save_processed_ids(self):
        self._processed_ids_file.write_text("\n".join(self._processed_ids))

    # ── OAuth ──────────────────────────────────────────────────────────────────

    def _authenticate(self) -> bool:
        """Authenticate with Gmail API. Returns True on success."""
        if not GOOGLE_AVAILABLE:
            self.logger.error(
                "Google API libraries not installed. Run:\n"
                "  pip install google-auth google-auth-oauthlib google-api-python-client"
            )
            return False

        if not self.credentials_path.exists():
            self.logger.error(
                f"Gmail credentials not found: {self.credentials_path}\n"
                "Follow docs/gmail_setup.md to set up OAuth credentials."
            )
            return False

        creds = None

        # Load saved token
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        # Refresh or re-authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                self.logger.info("Gmail token refreshed.")
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)
                self.logger.info("Gmail OAuth completed.")

            # Save token for next run
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json())

        self.service = build("gmail", "v1", credentials=creds)
        self.logger.info("Gmail API authenticated.")
        return True

    # ── BaseWatcher interface ──────────────────────────────────────────────────

    def check_for_updates(self) -> list:
        """Fetch unread important emails not yet processed."""
        if not self.service:
            return []

        try:
            result = (
                self.service.users()
                .messages()
                .list(userId="me", q=self.query, maxResults=20)
                .execute()
            )
            messages = result.get("messages", [])
            return [m for m in messages if m["id"] not in self._processed_ids]
        except Exception as e:
            self.logger.error(f"Gmail API error: {e}")
            return []

    def create_action_file(self, message: dict) -> Path:
        """Fetch full message and write a Needs_Action .md file."""
        msg_id = message["id"]

        try:
            full = (
                self.service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
        except Exception as e:
            self.logger.error(f"Failed to fetch message {msg_id}: {e}")
            return Path(msg_id)

        # Extract headers
        headers = {
            h["name"]: h["value"]
            for h in full.get("payload", {}).get("headers", [])
        }

        sender  = headers.get("From", "Unknown")
        subject = headers.get("Subject", "(No Subject)")
        date    = headers.get("Date", datetime.now().isoformat())
        snippet = full.get("snippet", "")

        # Determine priority
        label_ids = full.get("labelIds", [])
        priority = "high" if "IMPORTANT" in label_ids else "normal"

        content = f"""---
type: email
gmail_id: {msg_id}
from: {sender}
subject: {subject}
date: {date}
received: {datetime.now(timezone.utc).isoformat()}
priority: {priority}
status: pending
---

## Email Received

| Field   | Value |
|---------|-------|
| From    | `{sender}` |
| Subject | {subject} |
| Date    | {date} |
| Priority| {priority} |

## Preview

{snippet}

## Suggested Actions
- [ ] Read full email in Gmail
- [ ] Determine if reply is needed
- [ ] Draft reply (use /create-plan for complex replies)
- [ ] Move to /Done when handled

## Notes
_Add notes about this email here._
"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        action_path = self.needs_action / f"EMAIL_{timestamp}_{msg_id[:12]}.md"

        if DRY_RUN:
            self.logger.info(f"[DRY RUN] Would create: {action_path.name}")
        else:
            action_path.write_text(content, encoding="utf-8")
            self.logger.info(f"Created: {action_path.name} | From: {sender[:40]}")

        # Mark as processed
        self._processed_ids.add(msg_id)
        self._save_processed_ids()
        self.log_event("EMAIL_RECEIVED", f"id={msg_id} from={sender[:40]}")

        return action_path

    # ── Runner ─────────────────────────────────────────────────────────────────

    def run(self):
        if not self._authenticate():
            self.logger.error("Authentication failed — exiting.")
            return

        self.logger.info(f"Gmail query: '{self.query}'")
        self.logger.info(f"Check interval: {self.check_interval}s")
        if DRY_RUN:
            self.logger.info("[DRY RUN MODE]")

        stop_file = self.vault_path / "STOP.md"

        while True:
            if stop_file.exists():
                self.logger.warning("STOP.md detected — halting.")
                time.sleep(10)
                continue

            try:
                items = self.check_for_updates()
                if items:
                    self.logger.info(f"Found {len(items)} new email(s)")
                for item in items:
                    self.create_action_file(item)
            except KeyboardInterrupt:
                self.logger.info("Stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Error: {e}")
                self.log_event("ERROR", str(e))

            time.sleep(self.check_interval)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI Employee — Gmail Watcher (Silver Tier)")
    parser.add_argument("--vault",       default=os.getenv("VAULT_PATH", "AI_Employee_Vault"))
    parser.add_argument("--credentials", default=os.getenv("GMAIL_CREDENTIALS_PATH", "credentials/gmail_credentials.json"))
    parser.add_argument("--token",       default=os.getenv("GMAIL_TOKEN_PATH",       "credentials/gmail_token.json"))
    parser.add_argument("--interval",    type=int, default=120)
    parser.add_argument("--query",       default=DEFAULT_QUERY)
    parser.add_argument("--dry-run",     action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
        global DRY_RUN
        DRY_RUN = True

    watcher = GmailWatcher(
        vault_path=args.vault,
        credentials_path=args.credentials,
        token_path=args.token,
        check_interval=args.interval,
        query=args.query,
    )
    watcher.run()


if __name__ == "__main__":
    main()
