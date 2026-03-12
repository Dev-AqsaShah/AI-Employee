# Twitter/X Post — Gold Tier Skill

Draft and queue a tweet for the business account (280 character hard limit), routed through human-in-the-loop approval before publishing.

## Usage

```
/twitter-post "topic or goal"
/twitter-post           ← uses today's scheduled topic from Business_Goals.md
```

Examples:
```
/twitter-post "AI is changing how small businesses operate"
/twitter-post "quick tip on automating repetitive tasks"
```

## Instructions

1. Read `AI_Employee_Vault/Business_Goals.md` for current goals and brand voice.
2. Read `AI_Employee_Vault/Company_Handbook.md` — social media posts ALWAYS require human approval.
3. Check if a tweet already exists today:
   - Look for `Pending_Approval/TWITTER_<today>.md`, `Approved/TWITTER_<today>.md`, or `Done/TWITTER_<today>.md`
   - If found: report "Tweet already drafted today."
4. Draft a tweet with **HARD LIMIT of 280 characters**:
   - Punchy and direct — no filler words
   - One clear idea or insight per tweet
   - Optional: 1–2 relevant hashtags (only if they add value)
   - Optional: 1 emoji maximum
   - No corporate speak — sound human
   - End with a thought-provoking statement or question
   - **Count characters carefully before finalizing**
5. Write to `AI_Employee_Vault/Pending_Approval/TWITTER_<YYYY-MM-DD>.md`:

```markdown
---
type: twitter_post
topic: <topic>
drafted: <ISO timestamp>
status: pending_approval
char_count: <count>
---

# Tweet — <YYYY-MM-DD>

> **Topic:** <topic>
> **Char count:** <count> / 280

---

## Tweet Content

<tweet text here>

---

## Instructions
- **APPROVE:** Move to `/Approved/` — Twitter Watcher will auto-post it
- **EDIT:** Edit the Tweet Content above (keep under 280 chars), then move to `/Approved/`
- **REJECT:** Move to `/Rejected/`
```

6. Update `AI_Employee_Vault/Dashboard.md` — add to Recent Activity.
7. Log to `AI_Employee_Vault/Logs/YYYY-MM-DD.log`.
8. Report: "Tweet drafted (X/280 chars). Review in `Pending_Approval/TWITTER_<date>.md`."

## Auto-Post Flow

Once approved (file moved to `Approved/`):
- The **Twitter Watcher** (`watchers/twitter_watcher.py`) detects it automatically
- Posts to your Twitter/X account via Playwright browser automation
- Moves the file to `Done/` with posting timestamp

## Session Setup (one-time)

```bash
python watchers/twitter_watcher.py --setup
```
This opens a browser for you to log in. Session is saved automatically.

## Manual Trigger

```bash
python schedulers/twitter_scheduler.py --force       # Draft now
python schedulers/twitter_scheduler.py --dry-run     # Preview only
```

## Default Posting Days

Monday, Wednesday, Friday (configurable in `Business_Goals.md` via `twitter_posting_days:`)
