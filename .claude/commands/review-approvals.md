# Review Approvals — Silver Tier Skill

Show all items currently waiting for human approval, with a summary of what each requires and its risk level.

## Instructions

1. List all `.md` files in `AI_Employee_Vault/Pending_Approval/` (exclude `.gitkeep`).
2. For each file, read its frontmatter and content.
3. Classify risk level per `Company_Handbook.md`:
   - 🔴 HIGH: payments > $500, new payees, bulk emails, irreversible actions
   - 🟡 MEDIUM: payments $50–$500, emails to known contacts, social media posts
   - 🟢 LOW: file moves, draft creation, scheduling
4. Print a summary table:

```
Pending Approvals — 2026-02-27

# | File                        | Type       | Risk   | Summary
--|------------------------------|------------|--------|---------------------------
1 | LINKEDIN_2026-02-27.md      | social     | 🟡 MED | LinkedIn post draft
2 | EMAIL_invoice_acme.md       | email      | 🟡 MED | Invoice reply to Acme Corp
3 | PAYMENT_vendor_xyz.md       | payment    | 🔴 HIGH| $750 payment to new vendor
```

5. For each item, show the recommended action:
   - **To approve:** `move Pending_Approval/<file> → Approved/`
   - **To reject:** `move Pending_Approval/<file> → Rejected/`

6. Ask: "Which items would you like to approve or reject?"

## Bulk Approve (low-risk only)

If user says "approve all low-risk":
- Move all 🟢 LOW items to `Approved/`
- Leave 🟡 MEDIUM and 🔴 HIGH for individual review
- Log all moves

## Expiry Check

Flag any approval requests older than 24 hours — they may be stale and need re-evaluation.
