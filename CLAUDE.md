# AI Employee — CLAUDE.md

This is the Claude Code configuration file for the **Personal AI Employee (Gold Tier)**.

## Vault Location

All work happens inside the `AI_Employee_Vault/` directory in this repository.
When reading or writing files, always use paths relative to this repository root.

## Vault Structure

```
AI_Employee_Vault/
├── Dashboard.md          ← Real-time status overview (update after every action)
├── Company_Handbook.md   ← Rules of engagement — READ THIS FIRST
├── Business_Goals.md     ← Q1 objectives, metrics, and social media strategy
├── Inbox/                ← Files waiting to be triaged
├── Needs_Action/         ← Items requiring processing (Claude's primary queue)
├── Pending_Approval/     ← Actions awaiting human approval
├── Approved/             ← Human-approved actions ready to execute
├── Rejected/             ← Human-rejected actions (archive)
├── Plans/                ← Plan.md files created during reasoning
├── Done/                 ← Completed items (archive)
├── Logs/                 ← Audit logs (YYYY-MM-DD.log)
└── Briefings/            ← Daily/weekly CEO briefings
```

## Operating Rules

1. **Always read Company_Handbook.md before taking any action.**
2. **Update Dashboard.md after every significant action.**
3. **Log every action to Logs/YYYY-MM-DD.log.**
4. **Never perform external actions (send email, post to social media) without a file in /Approved/.**
5. **Check for STOP.md in vault root — if it exists, halt all autonomous actions.**
6. **All social media posts require human approval before publishing.**

## Available Agent Skills

Use these slash commands inside Claude Code:

### Core Skills

| Command              | Description                                        |
|----------------------|----------------------------------------------------|
| `/process-inbox`     | Process all pending Needs_Action items             |
| `/daily-briefing`    | Generate today's status briefing                   |
| `/vault-status`      | Quick snapshot of all vault folder counts          |
| `/move-to-done`      | Mark a specific item as complete                   |
| `/review-approvals`  | List all items awaiting human approval             |

### Planning & Execution

| Command              | Description                                        |
|----------------------|----------------------------------------------------|
| `/create-plan`       | Reason through a task and write a Plan.md          |
| `/execute-plan`      | Work through a Plan.md step by step                |
| `/schedule-briefing` | Set up cron/Task Scheduler for daily automation    |

### Social Media (Gold Tier)

| Command              | Description                                        |
|----------------------|----------------------------------------------------|
| `/linkedin-post`     | Draft a LinkedIn post (→ Pending_Approval)         |
| `/facebook-post`     | Draft a Facebook post (→ Pending_Approval)         |
| `/instagram-post`    | Draft an Instagram caption (→ Pending_Approval)    |
| `/twitter-post`      | Draft a tweet / 280 chars (→ Pending_Approval)     |

### Accounting & Reporting (Gold Tier)

| Command              | Description                                        |
|----------------------|----------------------------------------------------|
| `/ceo-briefing`      | Generate weekly CEO business audit report          |
| `/odoo-invoice`      | Create/list invoices via Odoo ERP                  |

### Autonomy (Gold Tier)

| Command              | Description                                        |
|----------------------|----------------------------------------------------|
| `/ralph-status`      | Check Ralph Wiggum Loop status / reset / stop      |
| `/gmail-watcher`     | Set up and check the Gmail watcher                 |

## Human-in-the-Loop Workflow

```
AI drafts post → Pending_Approval/<PLATFORM>_<date>.md
      ↓
You review in Obsidian
      ↓
Move to Approved/        ← drag & drop in Obsidian
      ↓
Watcher detects → auto-posts
      ↓
Moved to Done/
```

## Social Media Schedule

| Platform   | Default Posting Days       | Char Limit |
|------------|---------------------------|------------|
| LinkedIn   | Monday, Wednesday, Friday  | 1,300      |
| Facebook   | Tuesday, Thursday, Saturday| 500        |
| Instagram  | Tuesday, Thursday, Saturday| 2,200      |
| Twitter/X  | Monday, Wednesday, Friday  | 280        |

Customize in `Business_Goals.md`:
```
posting_days: Monday, Wednesday, Friday
instagram_posting_days: Tuesday, Thursday, Saturday
twitter_posting_days: Monday, Wednesday, Friday
```

## Watchers (run via Orchestrator)

Start everything with one command:
```bash
python orchestrator.py
```

Individual watchers:
```bash
python watchers/filesystem_watcher.py   # Monitor drop folder
python watchers/gmail_watcher.py        # Monitor Gmail
python watchers/linkedin_watcher.py     # Auto-post LinkedIn
python watchers/facebook_watcher.py     # Auto-post Facebook
python watchers/instagram_watcher.py    # Auto-post Instagram
python watchers/twitter_watcher.py      # Auto-post Twitter/X
python watchers/email_watcher.py        # Send emails via SMTP
python watchers/ralph_watcher.py        # Task chain daemon
```

## Session Setup (one-time per social platform)

```bash
python watchers/facebook_watcher.py --setup
python watchers/instagram_watcher.py --setup
python watchers/twitter_watcher.py --setup
```

## Emergency Stop

```bash
# Create STOP.md to halt all autonomous actions
echo "STOP" > AI_Employee_Vault/STOP.md

# Or use the skill:
# /ralph-status stop
```

## Odoo ERP (Gold Tier)

```bash
# Start Odoo + PostgreSQL
docker compose up -d

# Test MCP connection
python mcp_server/odoo_mcp.py --test

# Open dashboard: http://localhost:8069
```

## Security

- Never commit `.env` — it is in `.gitignore`
- All credentials go in `.env` only
- Sessions stored in `credentials/` (also gitignored)
- Human approval required for all external actions
