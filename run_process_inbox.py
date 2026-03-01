"""
Simulates the /process-inbox Agent Skill:
  1. Reads Company_Handbook.md
  2. Finds pending Needs_Action items
  3. Assesses each against handbook rules
  4. Moves to Pending_Approval (financial >= $50) or Done
  5. Logs + updates Dashboard
"""
import os, re
from pathlib import Path
from datetime import datetime, timezone

VAULT        = Path("AI_Employee_Vault")
NEEDS_ACTION = VAULT / "Needs_Action"
PENDING      = VAULT / "Pending_Approval"
DONE         = VAULT / "Done"
LOGS         = VAULT / "Logs"
DASHBOARD    = VAULT / "Dashboard.md"

now   = datetime.now(timezone.utc)
ts    = now.strftime("%Y-%m-%dT%H:%M:%SZ")
today = now.strftime("%Y-%m-%d")

# Step 1: read handbook
handbook = (VAULT / "Company_Handbook.md").read_text()
print("✓ Read Company_Handbook.md")

# Step 2: find pending items
pending_files = [
    f for f in NEEDS_ACTION.iterdir()
    if f.suffix == ".md" and f.name != ".gitkeep"
    and "status: pending" in f.read_text()
]
print(f"✓ Found {len(pending_files)} pending item(s)")

moved_to_pending = []
moved_to_done    = []

for f in pending_files:
    content = f.read_text()
    print(f"\n  Processing: {f.name}")

    # Step 3: assess against handbook rules
    amounts = [float(x.replace(",", "")) for x in re.findall(r'\$([\d,]+(?:\.\d+)?)', content)]
    max_amount = max(amounts) if amounts else 0

    if amounts and max_amount >= 50:
        decision = "pending_approval"
        reason   = f"Financial amount ${max_amount:,.2f} detected — handbook §2 requires approval (>=\$50)"
    else:
        decision = "done"
        reason   = "No financial/external action required — auto-approved per handbook §5"

    print(f"  Decision : {decision.upper()}")
    print(f"  Reason   : {reason}")

    # Step 4: update frontmatter + move
    updated = content.replace("status: pending", f"status: {decision}")
    updated += f"\n\n## AI Review [{ts}]\n- **Decision:** {decision.upper()}\n- **Reason:** {reason}\n"

    if decision == "pending_approval":
        dest = PENDING / f.name
        dest.write_text(updated)
        f.unlink()
        moved_to_pending.append(f.name)
        print(f"  → Moved to /Pending_Approval/")
    else:
        dest = DONE / f.name
        dest.write_text(updated)
        f.unlink()
        moved_to_done.append(f.name)
        print(f"  → Moved to /Done/")

# Step 5: log
log_lines = [
    f"[{ts}] [process-inbox] Processed {len(pending_files)} item(s). "
    f"Pending_Approval={len(moved_to_pending)} Done={len(moved_to_done)}"
]
for n in moved_to_pending:
    log_lines.append(f"  PENDING_APPROVAL: {n}")
for n in moved_to_done:
    log_lines.append(f"  DONE: {n}")

log_path = LOGS / f"{today}.log"
with open(log_path, "a") as lf:
    lf.write("\n".join(log_lines) + "\n")
print(f"\n✓ Logged to Logs/{today}.log")

# Step 6: update Dashboard
dash = DASHBOARD.read_text()
dash = re.sub(r'- \*\*Needs Action:\*\* \d+',    "- **Needs Action:** 0",               dash)
dash = re.sub(r'- \*\*Pending Approval:\*\* \d+', f"- **Pending Approval:** {len(moved_to_pending)}", dash)

# Increment Done count
def bump_done(m):
    cur = int(re.search(r'\d+', m.group()).group())
    return f"- **Done this week:** {cur + len(moved_to_done)}"
dash = re.sub(r'- \*\*Done this week:\*\* \d+', bump_done, dash)

# Add Recent Activity row
row = f"| {now.strftime('%Y-%m-%d %H:%M:%S')} | process-inbox: {len(pending_files)} item(s) — {len(moved_to_pending)} pending approval, {len(moved_to_done)} done |"
dash = dash.replace(
    "| Time (UTC)          | Action                                      |",
    "| Time (UTC)          | Action                                      |\n" + row
)
DASHBOARD.write_text(dash)
print("✓ Dashboard.md updated")

# Summary
print(f"""
╔══════════════════════════════════════════════╗
║  /process-inbox complete                     ║
╠══════════════════════════════════════════════╣
║  Items processed    : {len(pending_files):<24}║
║  → Pending Approval : {len(moved_to_pending):<24}║
║  → Done             : {len(moved_to_done):<24}║
║  Errors             : 0                      ║
╚══════════════════════════════════════════════╝
""")
