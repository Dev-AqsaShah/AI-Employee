# Execute Plan — Silver Tier Skill

Work through a Plan.md file step by step, executing auto-approved steps and routing approval-required steps through HITL workflow.

## Usage

```
/execute-plan PLAN_<name>.md
```

## Instructions

1. Read the specified plan from `AI_Employee_Vault/Plans/<filename>`.
2. Read `AI_Employee_Vault/Company_Handbook.md` for rules.
3. For each unchecked step `- [ ]`:
   a. **If auto-approved:** Execute the action, mark as done `- [x]`, log it.
   b. **If REQUIRES HUMAN APPROVAL:**
      - Create `AI_Employee_Vault/Pending_Approval/APPROVAL_<step>_<timestamp>.md`
      - Stop execution of dependent steps
      - Notify: "Step <N> requires your approval. See Pending_Approval folder."
4. After each step: save the updated plan (with checked boxes).
5. When ALL steps are done:
   - Set plan `status: completed`
   - Move plan to `AI_Employee_Vault/Done/`
   - Update `AI_Employee_Vault/Dashboard.md`
   - Log completion

## Output After Each Step

```
✓ Step 1: <action> — done
✓ Step 2: <action> — done
⏳ Step 3: <action> — AWAITING APPROVAL (see Pending_Approval/)
⏸ Step 4: blocked by Step 3
```
