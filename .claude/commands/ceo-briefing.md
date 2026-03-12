# CEO Briefing — Gold Tier Skill

Generate a comprehensive weekly business audit report for the CEO — covering activity logs, completed work, pending items, Odoo accounting data, and social media performance.

## Usage

```
/ceo-briefing           ← Generate this week's briefing
/ceo-briefing --force   ← Force generation (even if already done this week)
```

## Instructions

1. Read `AI_Employee_Vault/Business_Goals.md` for current targets and KPIs.
2. Read `AI_Employee_Vault/Company_Handbook.md` for context.
3. Collect data from the past 7 days:

   **Activity Logs** (`AI_Employee_Vault/Logs/`)
   - Count total actions logged
   - List key event types (BRIEFING_DONE, EMAIL_SENT, POST_PUBLISHED, etc.)
   - Flag any ERROR or EXCEPTION entries

   **Completed Work** (`AI_Employee_Vault/Done/`)
   - List all items completed this week
   - Group by type: emails, posts, plans, approvals

   **Pending Items**
   - `Needs_Action/` — list all pending items
   - `Pending_Approval/` — list items awaiting your review
   - Flag items older than 48 hours (stale)

   **Social Media** (from Done/ files)
   - Count posts published per platform (LinkedIn, Facebook, Instagram, Twitter)
   - List the topics covered this week

   **Odoo Accounting** (via MCP, if available)
   - Use `odoo_list_invoices` to get recent invoices
   - Use `odoo_get_balance` to get current account balance
   - Use `odoo_list_partners` to count active clients
   - If Odoo is unavailable, note it and continue

4. Generate the briefing using the data collected. Format:

```markdown
---
type: ceo_briefing
generated: <ISO timestamp>
week: <YYYY-WNN>
---

# CEO Weekly Briefing — Week of <date>

## Executive Summary
<2-3 sentences: what happened this week, key wins, concerns>

## Activity Stats
| Metric                    | This Week |
|---------------------------|-----------|
| Total actions logged       | X         |
| Emails processed           | X         |
| Posts published            | X         |
| Plans created              | X         |
| Items completed            | X         |
| Items awaiting approval    | X         |

## Completed Work
<bulleted list by category>

## Social Media
<per-platform summary>

## Financial Snapshot (Odoo)
<invoice summary, balance, client count — or "Odoo not configured">

## Pending Items
<list of what needs attention>

## Concerns & Anomalies
<errors, stale items, anything unusual>

## Recommendations for Next Week
<3-5 actionable suggestions based on data>
```

5. Save to `AI_Employee_Vault/Briefings/CEO_BRIEFING_<YYYY-MM-DD>.md`.
6. Update `AI_Employee_Vault/Dashboard.md` with a link to this briefing.
7. Log to `AI_Employee_Vault/Logs/YYYY-MM-DD.log`.
8. Report: "CEO Briefing generated: `Briefings/CEO_BRIEFING_<date>.md`"

## Automated Schedule

Runs automatically every Monday at 8:00 AM via the Orchestrator.

## Manual Run

```bash
python schedulers/ceo_briefing.py --force         # Generate now
python schedulers/ceo_briefing.py --dry-run --force  # Preview data only
python schedulers/ceo_briefing.py --force --email    # Generate + email to yourself
```
