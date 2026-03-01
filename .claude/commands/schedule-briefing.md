# Schedule Briefing — Silver Tier Skill

Set up automatic daily briefings using cron (Linux/Mac) or Task Scheduler (Windows) so the AI Employee runs without manual triggering.

## Usage

```
/schedule-briefing
```

## Instructions

1. Detect the operating system:
   - Check if `crontab` command exists → Linux/Mac
   - Otherwise → Windows (Task Scheduler)

2. **On Linux/Mac — set up cron:**

   Run:
   ```bash
   crontab -e
   ```
   Add this line (runs daily briefing at 8:00 AM):
   ```
   0 8 * * * cd /path/to/AI-Employee && .venv/bin/python run_process_inbox.py >> AI_Employee_Vault/Logs/cron.log 2>&1
   ```
   Also add watcher auto-restart (every 5 minutes check):
   ```
   */5 * * * * cd /path/to/AI-Employee && pgrep -f filesystem_watcher.py || .venv/bin/python watchers/filesystem_watcher.py &
   ```

3. **On Windows — set up Task Scheduler:**

   Create a scheduled task:
   ```cmd
   schtasks /create /tn "AI-Employee-Briefing" /tr "D:\AI-Employee\.venv\Scripts\python.exe D:\AI-Employee\run_process_inbox.py" /sc daily /st 08:00 /f
   ```
   For watcher auto-restart:
   ```cmd
   schtasks /create /tn "AI-Employee-Watcher" /tr "D:\AI-Employee\.venv\Scripts\python.exe D:\AI-Employee\watchers\filesystem_watcher.py" /sc onlogon /f
   ```

4. **Verify the schedule:**
   - Linux: `crontab -l` to list active crons
   - Windows: `schtasks /query /tn "AI-Employee-Briefing"`

5. Write schedule info to `AI_Employee_Vault/Dashboard.md` — add a "Scheduled Jobs" section.
6. Log the setup to `AI_Employee_Vault/Logs/YYYY-MM-DD.log`.

## Schedule Options

| Frequency | Cron Expression | Description          |
|-----------|----------------|----------------------|
| Daily 8AM | `0 8 * * *`    | Morning briefing     |
| Mon 8AM   | `0 8 * * 1`    | Weekly Monday CEO    |
| Every 30m | `*/30 * * * *` | Inbox check          |
| On boot   | `@reboot`      | Start watcher        |
