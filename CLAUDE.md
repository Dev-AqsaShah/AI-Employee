# AI Employee — CLAUDE.md

This is the Claude Code configuration file for the Personal AI Employee project (Bronze Tier).

## Vault Location

All work happens inside the `AI_Employee_Vault/` directory in this repository.
When reading or writing files, always use paths relative to this repository root.

## Vault Structure

```
AI_Employee_Vault/
├── Dashboard.md          ← Real-time status overview (update after every action)
├── Company_Handbook.md   ← Rules of engagement — READ THIS FIRST
├── Business_Goals.md     ← Q1 objectives and metrics
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
4. **Never perform external actions (send email, make payment) without a file in /Approved/.**
5. **Check for STOP.md in vault root — if it exists, halt all autonomous actions.**

## Available Skills

Use these slash commands inside Claude Code:

| Command              | Description                                   |
|----------------------|-----------------------------------------------|
| `/process-inbox`     | Process all pending Needs_Action items        |
| `/daily-briefing`    | Generate today's CEO briefing                 |
| `/move-to-done`      | Mark a specific item as complete              |
| `/vault-status`      | Quick snapshot of all vault folder counts     |

## Watchers

Run the filesystem watcher to monitor a drop folder:

```bash
# Install dependencies first
pip install -r requirements.txt

# Start the watcher (drop files into drop_folder/ to trigger)
python watchers/filesystem_watcher.py

# Dry run (no files written)
python watchers/filesystem_watcher.py --dry-run

# Custom paths
python watchers/filesystem_watcher.py --vault /path/to/vault --drop /path/to/drop
```

## Security

- Never commit `.env` — it is in `.gitignore`
- All credentials go in `.env` only
- See `.env.example` for the required variables
