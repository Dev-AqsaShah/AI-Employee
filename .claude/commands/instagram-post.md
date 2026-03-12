# Instagram Post — Gold Tier Skill

Draft and queue an Instagram caption for the business account, routed through human-in-the-loop approval before publishing.

## Usage

```
/instagram-post "topic or goal"
/instagram-post           ← uses today's scheduled topic from Business_Goals.md
```

Examples:
```
/instagram-post "behind the scenes of AI automation"
/instagram-post "productivity tips for entrepreneurs"
```

## Instructions

1. Read `AI_Employee_Vault/Business_Goals.md` for current goals, brand voice, and target audience.
2. Read `AI_Employee_Vault/Company_Handbook.md` — social media posts ALWAYS require human approval.
3. Check if an Instagram post already exists today:
   - Look for `Pending_Approval/INSTAGRAM_<today>.md`, `Approved/INSTAGRAM_<today>.md`, or `Done/INSTAGRAM_<today>.md`
   - If found: report "Instagram post already drafted today."
4. Draft an Instagram caption (aim for 150–300 chars; max 2200) that:
   - Opens with a strong first line (shown before "more")
   - Uses 2–4 relevant emojis
   - Ends with a question or call-to-action
   - Includes 3–5 hashtags at the end
   - Feels authentic and engaging
5. Write to `AI_Employee_Vault/Pending_Approval/INSTAGRAM_<YYYY-MM-DD>.md`:

```markdown
---
type: instagram_post
topic: <topic>
drafted: <ISO timestamp>
status: pending_approval
char_count: <count>
---

# Instagram Post — <YYYY-MM-DD>

> **Topic:** <topic>
> **Char count:** <count> / 2200

---

## Post Content

<caption text here>

---

## Instructions
- **APPROVE:** Move to `/Approved/` — Instagram Watcher will auto-post it
- **EDIT:** Edit the Post Content above, then move to `/Approved/`
- **REJECT:** Move to `/Rejected/`
```

6. Update `AI_Employee_Vault/Dashboard.md` — add to Recent Activity.
7. Log to `AI_Employee_Vault/Logs/YYYY-MM-DD.log`.
8. Report: "Instagram post drafted (X chars). Review in `Pending_Approval/INSTAGRAM_<date>.md`."

## Auto-Post Flow

Once approved (file moved to `Approved/`):
- The **Instagram Watcher** (`watchers/instagram_watcher.py`) detects it automatically
- Posts to your Instagram account via Playwright browser automation
- Moves the file to `Done/` with posting timestamp

## Session Setup (one-time)

```bash
python watchers/instagram_watcher.py --setup
```
This opens a browser for you to log in. Session is saved automatically.

## Manual Trigger

```bash
python schedulers/instagram_scheduler.py --force       # Draft now
python schedulers/instagram_scheduler.py --dry-run     # Preview only
```

## Default Posting Days

Tuesday, Thursday, Saturday (configurable in `Business_Goals.md` via `instagram_posting_days:`)
