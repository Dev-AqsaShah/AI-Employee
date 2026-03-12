# Facebook Post — Gold Tier Skill

Draft and queue a Facebook post for the business page, routed through human-in-the-loop approval before publishing.

## Usage

```
/facebook-post "topic or goal"
/facebook-post           ← uses today's scheduled topic from Business_Goals.md
```

Examples:
```
/facebook-post "announce our new AI consulting service"
/facebook-post "share tips on business automation"
```

## Instructions

1. Read `AI_Employee_Vault/Business_Goals.md` for current goals, services, and brand voice.
2. Read `AI_Employee_Vault/Company_Handbook.md` — social media posts ALWAYS require human approval.
3. Check if a Facebook post already exists today:
   - Look for `Pending_Approval/FACEBOOK_<today>.md`, `Approved/FACEBOOK_<today>.md`, or `Done/FACEBOOK_<today>.md`
   - If found: report "Facebook post already drafted today — use `/review-approvals` to approve it."
4. Draft a Facebook post (max 500 characters) that:
   - Starts with a hook (question or bold statement)
   - Highlights value, insight, or a tip
   - Includes 1–3 relevant hashtags
   - Ends with a call-to-action
   - Sounds authentic, not corporate
5. Write to `AI_Employee_Vault/Pending_Approval/FACEBOOK_<YYYY-MM-DD>.md`:

```markdown
---
type: facebook_post
topic: <topic>
drafted: <ISO timestamp>
status: pending_approval
char_count: <count>
---

# Facebook Post — <YYYY-MM-DD>

> **Topic:** <topic>
> **Char count:** <count> / 500

---

## Post Content

<post text here>

---

## Instructions
- **APPROVE:** Move to `/Approved/` — Facebook Watcher will auto-post it
- **EDIT:** Edit the Post Content above, then move to `/Approved/`
- **REJECT:** Move to `/Rejected/`
```

6. Update `AI_Employee_Vault/Dashboard.md` — add to Recent Activity.
7. Log to `AI_Employee_Vault/Logs/YYYY-MM-DD.log`.
8. Report: "Facebook post drafted (X chars). Review in `Pending_Approval/FACEBOOK_<date>.md`."

## Auto-Post Flow

Once approved (file moved to `Approved/`):
- The **Facebook Watcher** (`watchers/facebook_watcher.py`) detects it automatically
- Posts to your Facebook Page via Playwright browser automation
- Moves the file to `Done/` with posting timestamp

## Manual Trigger

To run the scheduler directly:
```bash
python schedulers/facebook_scheduler.py --force       # Draft now
python schedulers/facebook_scheduler.py --dry-run     # Preview only
```
