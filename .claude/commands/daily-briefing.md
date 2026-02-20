# Daily Briefing — AI Employee Skill

Generate a daily status briefing and update the vault Dashboard.

## Instructions

1. Read `AI_Employee_Vault/Business_Goals.md` for current goals and targets.
2. Read `AI_Employee_Vault/Dashboard.md` for current state.
3. Count items in each vault folder:
   - `AI_Employee_Vault/Needs_Action/` — pending items
   - `AI_Employee_Vault/Pending_Approval/` — awaiting human decision
   - `AI_Employee_Vault/Done/` — completed today (files modified today)
4. Check `AI_Employee_Vault/Logs/` for today's activity log.
5. Identify any items in `Needs_Action/` that are older than 24 hours (stale items).
6. Write a new briefing file at:
   `AI_Employee_Vault/Briefings/YYYY-MM-DD_Daily_Briefing.md`
   using the CEO Briefing template structure (Executive Summary, Stats, Completed, Pending, Stale Items, Suggestions).
7. Update `AI_Employee_Vault/Dashboard.md` with the latest counts and a link to today's briefing.

## Output Format

The briefing file should include:
- **Executive Summary** (1-2 sentences)
- **Vault Stats** (item counts per folder)
- **Completed Today** (list from Done/)
- **Awaiting Approval** (list from Pending_Approval/)
- **Stale Items** (older than 24h in Needs_Action/)
- **Suggestions** (based on patterns observed)
