# AI Employee — CLAUDE.md

This is the Claude Code configuration file for the **Personal AI Employee (Platinum Tier)**.

## Vault Location

All work happens inside the `AI_Employee_Vault/` directory in this repository.
When reading or writing files, always use paths relative to this repository root.

## Vault Structure

```
AI_Employee_Vault/
├── Dashboard.md              ← Real-time status overview (LOCAL only writes this)
├── Company_Handbook.md       ← Rules of engagement — READ THIS FIRST
├── Business_Goals.md         ← Q1 objectives, metrics, and social media strategy
├── Inbox/                    ← Files waiting to be triaged
├── Needs_Action/             ← Items requiring processing (primary queue)
│   ├── cloud/                ← Cloud-specific tasks
│   └── local/                ← Local-specific tasks
├── In_Progress/              ← Claimed items (claim-by-move rule)
│   ├── cloud/                ← Items currently being processed by cloud agent
│   └── local/                ← Items currently being processed by local agent
├── Pending_Approval/         ← Actions awaiting human approval
│   ├── cloud/                ← Drafted by cloud, awaiting Local approval
│   └── local/                ← Drafted by local
├── Approved/                 ← Human-approved actions ready to execute
├── Rejected/                 ← Human-rejected actions (archive)
├── Plans/                    ← Plan.md files created during reasoning
│   ├── cloud/                ← Cloud agent plans
│   └── local/                ← Local agent plans
├── Updates/                  ← Cloud writes status updates here; Local merges into Dashboard
├── Signals/                  ← Local writes directives to Cloud here
├── Done/                     ← Completed items (archive)
├── Logs/                     ← Audit logs (YYYY-MM-DD.log)
└── Briefings/                ← Daily/weekly CEO briefings
```

## Operating Rules

1. **Always read Company_Handbook.md before taking any action.**
2. **Update Dashboard.md after every significant action — LOCAL AGENT ONLY writes Dashboard.md.**
3. **Log every action to Logs/YYYY-MM-DD.log.**
4. **Never perform external actions (send email, post to social media) without a file in /Approved/.**
5. **Check for STOP.md in vault root — if it exists, halt all autonomous actions.**
6. **All social media posts require human approval before publishing.**
7. **Claim-by-move rule: Before processing any Needs_Action item, claim it by moving to In_Progress/<agent_id>/. If move fails, skip it (another agent has it).**
8. **Cloud never sends/posts — it only drafts to Pending_Approval/cloud/. Local approves and executes.**

## Work-Zone Specialization (Platinum Tier)

| Zone | Owner | Responsibilities |
|------|-------|-----------------|
| Cloud | Cloud Agent | Email triage, draft replies, social post drafts/scheduling |
| Local | Local Agent | Approvals, WhatsApp, payments, banking, final send/post |

**Single-writer rule:** Only the Local agent writes to `Dashboard.md`.
Cloud agent writes status to `Updates/` — Local merges them.

## Claim-by-Move Rule (Platinum Tier)

When both cloud and local agents could process the same item:

```
1. Item appears in /Needs_Action/
2. Agent calls claim_item(path) → moves to /In_Progress/<agent_id>/
3. If move succeeds: agent processes it
4. If move fails (FileNotFoundError): another agent claimed it — skip
5. After processing: move to Done/ or Pending_Approval/
```

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

## Platinum Tier: Cloud + Local Communication Flow

```
Email arrives (while Local offline)
      ↓
Cloud Gmail Watcher detects → writes Needs_Action/
      ↓
Cloud claims item (claim-by-move) → In_Progress/cloud/
      ↓
Cloud drafts reply → Pending_Approval/cloud/EMAIL_REPLY_*.md
      ↓
Cloud writes status → Updates/UPDATE_*.md
      ↓
Git push (vault sync)
      ↓
Local wakes up → git pull → sees Pending_Approval/cloud/
      ↓
Human approves (move to Approved/)
      ↓
Local Email Watcher detects Approved/ → sends email via MCP
      ↓
Logged → moved to Done/
```

## Social Media Schedule

| Platform   | Default Posting Days       | Char Limit |
|------------|---------------------------|------------|
| LinkedIn   | Monday, Wednesday, Friday  | 1,300      |
| Facebook   | Tuesday, Thursday, Saturday| 500        |
| Instagram  | Tuesday, Thursday, Saturday| 2,200      |
| Twitter/X  | Monday, Wednesday, Friday  | 280        |

Customize in `Business_Goals.md`.

## Watchers — Local (run via orchestrator.py)

Start everything with one command:
```bash
python orchestrator.py
```

Individual watchers:
```bash
python watchers/filesystem_watcher.py   # Monitor drop folder
python watchers/gmail_watcher.py        # Monitor Gmail
python watchers/linkedin_watcher.py     # Auto-post LinkedIn (after approval)
python watchers/facebook_watcher.py     # Auto-post Facebook (after approval)
python watchers/instagram_watcher.py    # Auto-post Instagram (after approval)
python watchers/twitter_watcher.py      # Auto-post Twitter/X (after approval)
python watchers/email_watcher.py        # Send emails via SMTP
python watchers/whatsapp_watcher.py     # WhatsApp monitor (LOCAL only)
python watchers/ralph_watcher.py        # Task chain daemon
```

## Watchers — Cloud (run via cloud_orchestrator.py)

```bash
python cloud_orchestrator.py            # Start cloud agent
```

Cloud runs ONLY: filesystem_watcher, gmail_watcher, email_watcher, ralph_watcher.
Cloud does NOT run: whatsapp_watcher, linkedin/facebook/instagram/twitter_watcher.

## Session Setup (one-time per social platform)

```bash
python watchers/facebook_watcher.py --setup
python watchers/instagram_watcher.py --setup
python watchers/twitter_watcher.py --setup
python watchers/whatsapp_watcher.py --setup   # LOCAL only — never on cloud
```

## Vault Sync (Platinum Tier)

```bash
python scripts/sync_vault.py --sync     # Pull then push
python scripts/sync_vault.py --watch    # Auto-sync every 5 minutes
```

## Emergency Stop

```bash
# Create STOP.md to halt all autonomous actions (both cloud and local)
echo "STOP" > AI_Employee_Vault/STOP.md

# Send stop signal to cloud agent
echo "STOP_CLOUD" > AI_Employee_Vault/Signals/STOP_$(date +%Y%m%d_%H%M%S).md
python scripts/sync_vault.py --push
```

## Odoo ERP (Gold Tier)

```bash
# Start Odoo + PostgreSQL (local)
docker compose up -d

# Test MCP connection
python mcp_server/odoo_mcp.py --test

# Open dashboard: http://localhost:8069
```

## Cloud Deployment (Platinum Tier)

```bash
# One-time setup on Oracle/AWS VM:
ssh -i credentials/ai-key-2.pem ubuntu@<your-vm-ip>
git clone https://github.com/Dev-AqsaShah/AI-Employee
cd AI-Employee
bash scripts/deploy_cloud.sh

# Health monitoring
python scripts/health_monitor.py --watch
```

## Security

- Never commit `.env` — it is in `.gitignore`
- All credentials go in `.env` only
- Sessions stored in `credentials/` (also gitignored)
- Human approval required for all external actions
- Cloud never stores WhatsApp sessions or banking credentials
- Vault sync via Git syncs only markdown — secrets never sync
