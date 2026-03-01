# LinkedIn Post — Silver Tier Skill

Automatically draft and queue a LinkedIn post to generate business leads, then route it through the HITL approval workflow before publishing.

## Usage

```
/linkedin-post "topic or goal"
```

Example:
```
/linkedin-post "promote our AI consulting services for Q1 2026"
```

## Instructions

1. Read `AI_Employee_Vault/Business_Goals.md` to understand current objectives and services.
2. Read `AI_Employee_Vault/Company_Handbook.md` — Section 5 (Autonomy Thresholds): social media posts ALWAYS require human approval before sending.
3. Draft a professional LinkedIn post (max 1,300 characters) that:
   - Highlights a specific value proposition or insight
   - Includes a call-to-action
   - Uses 3–5 relevant hashtags
   - Sounds human, not robotic
4. Write the draft to `AI_Employee_Vault/Pending_Approval/LINKEDIN_<YYYY-MM-DD>.md` with this frontmatter:
   ```
   ---
   type: linkedin_post
   status: pending_approval
   created: <ISO timestamp>
   character_count: <count>
   ---
   ```
5. Update `AI_Employee_Vault/Dashboard.md` — add to Recent Activity.
6. Log the action to `AI_Employee_Vault/Logs/YYYY-MM-DD.log`.
7. Tell the user: "LinkedIn post drafted and saved to Pending_Approval. Review and move to /Approved/ to publish."

## Approval Workflow

- **Approve:** Move file from `Pending_Approval/` → `Approved/`
- **Reject:** Move file to `Rejected/`
- After approval: run `/publish-linkedin` to send via MCP (Silver+)

## Post Quality Guidelines

- Lead with insight, not self-promotion
- Include a specific number or stat if possible
- End with a question to drive engagement
- Keep paragraphs short (1–2 sentences)
