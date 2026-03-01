# Personal AI Employee — Bronze Tier

> *Your life and business on autopilot. Local-first, agent-driven, human-in-the-loop.*

A **Bronze Tier** implementation of the [Personal AI Employee Hackathon](./Personal%20AI%20Employee%20Hackathon%200_%20Building%20Autonomous%20FTEs%20in%202026.md).

---

## What's Included (Bronze Tier)

| Requirement                                      | Status |
|--------------------------------------------------|--------|
| Obsidian vault with `Dashboard.md`               | ✅     |
| Obsidian vault with `Company_Handbook.md`        | ✅     |
| Basic folder structure (Inbox, Needs_Action, Done) | ✅   |
| Filesystem Watcher script                        | ✅     |
| Claude Code reading/writing to vault             | ✅     |
| Agent Skills (Claude slash commands)             | ✅     |

---

## Architecture

```
drop_folder/          ← Drop files here to trigger the watcher
    │
    ▼
watchers/
  filesystem_watcher.py   ← Monitors drop_folder, creates Needs_Action items
    │
    ▼
AI_Employee_Vault/
  ├── Inbox/              ← Copies of dropped files
  ├── Needs_Action/       ← .md action items for Claude to process
  ├── Pending_Approval/   ← Actions needing your approval
  ├── Approved/           ← Approved actions ready to execute
  ├── Done/               ← Completed items
  ├── Plans/              ← Claude's reasoning plans
  ├── Logs/               ← Audit trail
  ├── Briefings/          ← Daily CEO briefings
  ├── Dashboard.md        ← Real-time status
  ├── Company_Handbook.md ← Rules of engagement
  └── Business_Goals.md  ← Q1 objectives
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set VAULT_PATH and DROP_PATH if needed
```

### 3. Start the filesystem watcher

```bash
python watchers/filesystem_watcher.py
```

Drop any file into `drop_folder/` — the watcher will copy it to `Inbox/` and create a `Needs_Action` item automatically.

### 4. Use Claude Agent Skills

Inside Claude Code (from this directory):

```
/process-inbox      — Process all pending Needs_Action items
/daily-briefing     — Generate today's CEO briefing
/vault-status       — Quick status snapshot
/move-to-done       — Mark an item complete
```

### 5. Dry-run mode (safe for development)

```bash
DRY_RUN=true python watchers/filesystem_watcher.py
# or
python watchers/filesystem_watcher.py --dry-run
```

---

## Emergency Stop

Create a `STOP.md` file in the vault root to halt all autonomous watcher actions:

```bash
touch AI_Employee_Vault/STOP.md
```

Remove it to resume:

```bash
rm AI_Employee_Vault/STOP.md
```

---

## Security

- `.env` is in `.gitignore` — never commit credentials
- All sensitive data lives in `.env` only
- The watcher runs in `DRY_RUN=true` mode by default until you opt in
- See `AI_Employee_Vault/Company_Handbook.md` for permission boundaries

---

## Next Steps (Silver Tier)

- Add Gmail Watcher (OAuth-based email monitoring)
- Add LinkedIn auto-posting
- Add Claude reasoning loop that creates `Plan.md` files
- Add Email MCP server for sending approved emails
- Add cron scheduling for daily briefings

---

## Hackathon

- **Tier:** Bronze
- **Hackathon:** Personal AI Employee Hackathon 0
- **Engine:** Claude Code
- **Knowledge Base:** Obsidian (local Markdown)
