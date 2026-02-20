# Move to Done — AI Employee Skill

Mark a specific Needs_Action or Pending_Approval item as complete and move it to /Done/.

## Usage

Provide the filename or partial name: `/move-to-done FILE_20260220_report.md`

## Instructions

1. Find the specified file in `AI_Employee_Vault/Needs_Action/` or `AI_Employee_Vault/Pending_Approval/`.
2. Update the file's frontmatter: set `status: done` and add `completed: <current ISO timestamp>`.
3. Move the file to `AI_Employee_Vault/Done/`.
4. Log the action: `AI_Employee_Vault/Logs/YYYY-MM-DD.log`.
5. Update `AI_Employee_Vault/Dashboard.md` — decrement the relevant counter and add to Recent Activity.
6. Print a confirmation: "Moved [filename] to /Done/ at [timestamp]."

## Safety

- Never move files from `/Approved/` or `/Rejected/` — those are managed by the approval workflow.
- If the file is not found, list the current contents of `/Needs_Action/` and `/Pending_Approval/` so the user can choose the correct file.
