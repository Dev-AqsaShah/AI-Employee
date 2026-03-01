# Gmail Watcher — Silver Tier Skill

Set up, start, or check the status of the Gmail Watcher that monitors important unread emails and creates Needs_Action items.

## Setup Instructions (first time only)

1. Check if `credentials/gmail_credentials.json` exists in the project root.
   - If NOT: tell the user to follow the Gmail OAuth setup in `docs/gmail_setup.md`
2. Check if `watchers/gmail_watcher.py` exists — it should already be present.
3. Check `.env` for `GMAIL_CREDENTIALS_PATH` — set it if missing.

## Start the Watcher

Run in a dedicated terminal:
```bash
python watchers/gmail_watcher.py
```

Or with custom options:
```bash
python watchers/gmail_watcher.py --vault AI_Employee_Vault --interval 120
```

## What It Does

- Polls Gmail every 120 seconds for **unread + important** emails
- Skips emails already processed (tracks IDs in `AI_Employee_Vault/.processed_gmail_ids`)
- For each new email: creates `AI_Employee_Vault/Needs_Action/EMAIL_<id>.md` with:
  - Sender, subject, date, snippet
  - Priority tag (high/normal based on importance)
  - Suggested actions checklist
- Logs all activity to `AI_Employee_Vault/Logs/YYYY-MM-DD.log`

## Check Status

List recent Gmail action files:
```bash
ls AI_Employee_Vault/Needs_Action/EMAIL_*.md
```

## Troubleshooting

- **403 Forbidden**: Gmail API not enabled in Google Cloud Console — go to console.cloud.google.com
- **Token expired**: Delete `credentials/gmail_token.json` and re-run to re-authenticate
- **No emails detected**: Check that `is:unread is:important` filter matches your inbox
