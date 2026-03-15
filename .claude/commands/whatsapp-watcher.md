# WhatsApp Watcher — Gold Tier Skill

Monitor incoming WhatsApp messages and send approved replies via WhatsApp Web automation.

## Usage

```
/whatsapp-watcher          ← show status and instructions
/whatsapp-watcher setup    ← guide for QR session setup
/whatsapp-watcher check    ← check Inbox for new WA messages
```

## Instructions

1. Read `AI_Employee_Vault/Company_Handbook.md` — all external actions require approval.
2. Check `credentials/whatsapp_session/state.json` — if missing, setup needed.
3. Check `AI_Employee_Vault/Inbox/` for any `WHATSAPP_*.md` files.
4. For each unprocessed WhatsApp message:
   - Read the message content
   - Decide: needs reply? needs action? informational only?
   - If reply needed: draft `AI_Employee_Vault/Pending_Approval/WHATSAPP_REPLY_<YYYY-MM-DD>_<contact>.md`
5. Update Dashboard and log.

## Reply File Format

```markdown
---
type: whatsapp_reply
contact: <exact contact name as in WhatsApp>
drafted: <ISO timestamp>
status: pending_approval
---

# WhatsApp Reply — <contact> — <YYYY-MM-DD>

> **To:** <contact>
> **Re:** <original message summary>

---

## Reply Content

<your reply message here>

---

## Instructions
- **APPROVE:** Move to `/Approved/` — WhatsApp Watcher will auto-send it
- **EDIT:** Edit Reply Content above, then move to `/Approved/`
- **REJECT:** Move to `/Rejected/`
```

## Watcher Commands

```bash
# One-time setup (scan QR code)
python watchers/whatsapp_watcher.py --setup

# Check new messages once
python watchers/whatsapp_watcher.py --check-now

# Send approved replies once
python watchers/whatsapp_watcher.py --send-now

# Full watch mode (monitor + send loop)
python watchers/whatsapp_watcher.py

# Test without sending
python watchers/whatsapp_watcher.py --dry-run --check-now
```

## Flow

```
New WhatsApp message
      ↓
--check-now → Inbox/WHATSAPP_*.md
      ↓
/process-inbox → Claude drafts reply
      ↓
Pending_Approval/WHATSAPP_REPLY_*.md
      ↓
You approve → move to Approved/
      ↓
--send-now → reply sent on WhatsApp
      ↓
Done/WHATSAPP_REPLY_*.md
```
