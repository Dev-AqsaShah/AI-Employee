# Process Inbox — AI Employee Skill

Scan the vault's `/Needs_Action/` folder for pending items and process each one according to the rules in `Company_Handbook.md`.

## Instructions

1. Read `AI_Employee_Vault/Company_Handbook.md` to understand the rules of engagement.
2. Read `AI_Employee_Vault/Dashboard.md` to understand current state.
3. List all `.md` files in `AI_Employee_Vault/Needs_Action/` that have `status: pending` in their frontmatter.
4. For each pending item:
   a. Read the file carefully.
   b. Determine the required action based on the handbook rules.
   c. If the action is safe to take autonomously (per the handbook): log the action and move the file to `/Done/`.
   d. If the action requires human approval: create an approval file in `/Pending_Approval/` with the details, and update the original file's status to `awaiting_approval`.
   e. If the item is unclear: create a note in `/Plans/` explaining what information is needed.
5. Update `AI_Employee_Vault/Dashboard.md` with a summary of what was processed.
6. Log all actions to `AI_Employee_Vault/Logs/YYYY-MM-DD.log`.

## Output

After processing, print a summary:
- How many items were processed
- How many moved to Done
- How many are awaiting approval
- Any errors or unclear items
