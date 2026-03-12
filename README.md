# Personal AI Employee — Gold Tier

> *Your life and business on autopilot. Local-first, agent-driven, human-in-the-loop.*

A fully autonomous AI Employee powered by **Claude Code** + **Obsidian** that manages your business 24/7 — reading emails, posting on social media, generating CEO briefings, and chaining tasks together automatically.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              PERSONAL AI EMPLOYEE                    │
│                                                      │
│  PERCEPTION (Watchers)                               │
│  ├── gmail_watcher.py     — monitors Gmail           │
│  ├── linkedin_watcher.py  — monitors LinkedIn        │
│  ├── facebook_watcher.py  — posts to Facebook        │
│  ├── instagram_watcher.py — posts to Instagram       │
│  ├── twitter_watcher.py   — posts to Twitter/X       │
│  ├── email_watcher.py     — sends emails via SMTP    │
│  ├── filesystem_watcher.py— monitors drop folder     │
│  └── ralph_watcher.py     — autonomous task chains   │
│                                                      │
│  REASONING (Claude Code)                             │
│  └── Vault files → Claude reads/writes → Actions    │
│                                                      │
│  ACTION (MCP Servers)                                │
│  ├── email_mcp.py         — send emails              │
│  └── odoo_mcp.py          — accounting (Odoo ERP)    │
│                                                      │
│  ORCHESTRATION                                       │
│  └── orchestrator.py      — master process manager  │
└─────────────────────────────────────────────────────┘
```

**Memory/GUI:** Obsidian vault (`AI_Employee_Vault/`) — local markdown files
**Brain:** Claude Code — reasoning engine
**Hands:** MCP servers — external actions
**Senses:** Watchers — monitors all inputs 24/7

---

## Tier

**Gold Tier** — Autonomous Employee

| Feature | Status |
|---------|--------|
| Filesystem watcher | ✅ |
| Gmail watcher | ✅ |
| LinkedIn auto-posting | ✅ |
| Facebook auto-posting | ✅ |
| Instagram auto-posting | ✅ |
| Twitter/X auto-posting | ✅ |
| Email MCP server | ✅ |
| Odoo accounting MCP | ✅ |
| CEO Weekly Briefing | ✅ |
| Ralph Wiggum Loop | ✅ |
| Human-in-the-loop approvals | ✅ |
| Audit logging | ✅ |
| Error recovery + auto-restart | ✅ |

---

## Quick Start

### 1. Install dependencies

```bash
pip install watchdog python-dotenv playwright google-auth google-auth-oauthlib google-api-python-client anthropic
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Setup social media sessions (run once each)

```bash
# Facebook
python watchers/facebook_watcher.py --setup

# Instagram
python watchers/instagram_watcher.py --setup

# Twitter/X
python watchers/twitter_watcher.py --setup
```

### 4. Start the orchestrator

```bash
python orchestrator.py
```

That's it. Everything runs automatically.

---

## Vault Structure

```
AI_Employee_Vault/
├── Dashboard.md          ← Real-time status (check here)
├── Company_Handbook.md   ← AI rules of engagement
├── Business_Goals.md     ← Revenue targets + content strategy
├── Inbox/                ← Files waiting to be processed
├── Needs_Action/         ← AI's work queue
├── Pending_Approval/     ← Waiting for YOUR approval
├── Approved/             ← Approved → AI will execute
├── Rejected/             ← Rejected actions
├── Done/                 ← Completed items
├── Briefings/            ← CEO weekly briefings
├── Logs/                 ← Daily audit logs
└── Plans/                ← AI reasoning plans
```

---

## Human-in-the-Loop Workflow

```
AI drafts post
      ↓
Pending_Approval/LINKEDIN_2026-03-11.md
      ↓
You review in Obsidian
      ↓
Move to Approved/   ← drag & drop in Obsidian
      ↓
Watcher detects → auto-posts
      ↓
Moved to Done/
```

---

## Social Media Schedule

| Platform | Default Days | Char Limit |
|----------|-------------|------------|
| LinkedIn | Mon, Wed, Fri | 1300 |
| Facebook | Tue, Thu, Sat | 500 |
| Instagram | Tue, Thu, Sat | 2200 |
| Twitter/X | Mon, Wed, Fri | 280 |

Customize in `Business_Goals.md`:
```
posting_days: Monday, Wednesday, Friday
instagram_posting_days: Tuesday, Thursday, Saturday
twitter_posting_days: Monday, Wednesday, Friday
```

---

## CEO Weekly Briefing

Every Monday at 8:00 AM, the AI generates a full business audit:

```bash
# Manual run
python schedulers/ceo_briefing.py --force

# Preview data (no API call)
python schedulers/ceo_briefing.py --dry-run --force

# Generate + email
python schedulers/ceo_briefing.py --force --email
```

Output saved to: `AI_Employee_Vault/Briefings/CEO_BRIEFING_YYYY-MM-DD.md`

---

## Ralph Wiggum Loop

Autonomous task chaining. When a task is completed, the next task is automatically queued.

Add to any Done/ file:
```yaml
---
next_action: Send invoice to client
---
```

Ralph Watcher detects this and creates the next task automatically.

**Claude Code Stop Hook** (`scripts/ralph_check.py`) — runs after every Claude Code response, checks for pending work, keeps Claude working until done.

---

## Odoo Accounting (Self-Hosted ERP)

```bash
# Start Odoo + PostgreSQL
docker compose up -d

# Open browser: http://localhost:8069
# Create database, then use Odoo normally

# Test MCP connection
python mcp_server/odoo_mcp.py --test
```

MCP tools available to Claude:
- `odoo_list_partners` — list clients
- `odoo_create_invoice` — create invoice
- `odoo_list_invoices` — list invoices
- `odoo_get_balance` — account balance
- `odoo_create_expense` — log expense

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ | Claude API key (console.anthropic.com) |
| `LINKEDIN_EMAIL` | Social | LinkedIn login |
| `LINKEDIN_PASSWORD` | Social | LinkedIn password |
| `FACEBOOK_EMAIL` | Social | Facebook login |
| `FACEBOOK_PASSWORD` | Social | Facebook password |
| `FACEBOOK_PAGE_URL` | Social | Your Facebook Page URL |
| `INSTAGRAM_USERNAME` | Social | Instagram username |
| `INSTAGRAM_PASSWORD` | Social | Instagram password |
| `TWITTER_USERNAME` | Social | Twitter/X username |
| `TWITTER_PASSWORD` | Social | Twitter/X password |
| `EMAIL_FROM` | Email | Gmail address |
| `EMAIL_APP_PASSWORD` | Email | Gmail App Password |
| `ODOO_URL` | Odoo | http://localhost:8069 |
| `ODOO_DB` | Odoo | Database name |

---

## Security

- **Never commit `.env`** — it's in `.gitignore`
- All credentials in `.env` only
- Sessions stored in `credentials/` (also gitignored)
- Human approval required for all external actions
- `STOP.md` in vault root halts all autonomous actions
- `DRY_RUN=true` prevents all real actions (safe for testing)

---

## Stopping the AI Employee

```bash
# Graceful stop
Ctrl+C

# Emergency stop (creates STOP.md)
echo "STOP" > AI_Employee_Vault/STOP.md
```

---

## Architecture Decisions & Lessons Learned

1. **File-based communication** — using markdown files as the message bus between watchers and Claude is simple, debuggable, and human-readable

2. **No API for social media** — Facebook, Instagram, Twitter all use Playwright browser automation. Zero API keys, zero verification required.

3. **Human-in-the-loop by default** — every external action requires approval. This prevents mistakes and builds trust over time.

4. **Obsidian as the GUI** — the vault is visible in Obsidian, giving a real-time dashboard without building any web UI.

5. **Orchestrator auto-restart** — crashed watchers restart automatically. The system is resilient by design.

6. **Ralph Wiggum Loop** — the Stop hook pattern solves the "lazy agent" problem. Claude keeps working until everything is done.

---

*Built for the Personal AI Employee Hackathon 0 — Gold Tier*
*Powered by Claude Code + Obsidian + Playwright + Odoo*
