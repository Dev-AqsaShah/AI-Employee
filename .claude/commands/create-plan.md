# Create Plan — Silver Tier Skill

Claude's reasoning loop: read a task or Needs_Action item, think through it step by step, and write a structured Plan.md file with checkboxes for execution.

## Usage

```
/create-plan <filename or description>
```

Examples:
```
/create-plan EMAIL_20260226_client_inquiry.md
/create-plan "respond to Acme Corp invoice request"
/create-plan "set up weekly social media schedule"
```

## Instructions

1. **Read the source:**
   - If a filename is given: read `AI_Employee_Vault/Needs_Action/<filename>`
   - If a description is given: use it as the task context
   - Also read `AI_Employee_Vault/Company_Handbook.md` for rules
   - Also read `AI_Employee_Vault/Business_Goals.md` for context

2. **Reason through the task:**
   - What is the end goal?
   - What information is already available?
   - What is missing / needs to be looked up?
   - Which steps require human approval (per handbook)?
   - What is the correct order of operations?

3. **Write the Plan.md file** to `AI_Employee_Vault/Plans/PLAN_<timestamp>_<slug>.md`:

```markdown
---
type: plan
source: <original file or description>
created: <ISO timestamp>
status: pending_execution
requires_approval: <yes/no>
---

## Objective
<One sentence goal>

## Context
<Relevant background from source file and business goals>

## Steps
- [ ] Step 1: <action> — auto-approved
- [ ] Step 2: <action> — auto-approved
- [ ] Step 3: <action> — REQUIRES HUMAN APPROVAL (reason: <why>)
- [ ] Step 4: <action> — auto-approved

## Risks & Notes
<Any ambiguities, missing info, or edge cases>

## Definition of Done
<What does "complete" look like?>
```

4. Update the source file's status to `status: planned` and add a link to the Plan.
5. Log the action to `AI_Employee_Vault/Logs/YYYY-MM-DD.log`.
6. Update `AI_Employee_Vault/Dashboard.md`.
7. Print: "Plan created: Plans/PLAN_<timestamp>_<slug>.md — <N> steps, <M> require approval."

## Execution

After reviewing the plan, run `/execute-plan PLAN_<name>.md` to work through each step.
