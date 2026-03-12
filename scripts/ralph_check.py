"""
ralph_check.py — Ralph Wiggum Loop: Claude Code Stop Hook

Runs automatically when Claude Code finishes a response.
Checks the vault for pending work — if found, blocks Claude from
stopping and feeds the next task back, creating an autonomous loop.

Named after Ralph Wiggum: "I'm helping!" — keeps going until done.

How it works:
  1. Claude Code calls this script after every response (Stop hook)
  2. Script scans vault for:
     - Needs_Action/ items with auto_execute: true
     - Approved/ items waiting to be processed
     - Chained tasks (next_action: field in completed items)
  3. If work found: outputs JSON block → Claude continues
  4. If nothing left: exits 0 → Claude stops normally

Claude Code hook output format:
  {"decision": "block", "reason": "<task description>"}  ← Claude continues
  (exit 0, no output)                                      ← Claude stops
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime

# ── Config ───────────────────────────────────────────────────────────────────────

VAULT_PATH   = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
NEEDS_ACTION = VAULT_PATH / "Needs_Action"
APPROVED     = VAULT_PATH / "Approved"
DONE         = VAULT_PATH / "Done"
LOGS         = VAULT_PATH / "Logs"

# Safety: never loop more than N times in a session
MAX_LOOP_COUNT = int(os.getenv("RALPH_MAX_LOOPS", "5"))
LOOP_COUNTER_FILE = Path(".ralph_loop_count")


# ── Loop counter (prevents infinite loops) ───────────────────────────────────────

def get_loop_count() -> int:
    """Read current loop count for this session."""
    if not LOOP_COUNTER_FILE.exists():
        return 0
    try:
        return int(LOOP_COUNTER_FILE.read_text().strip())
    except Exception:
        return 0


def increment_loop_count() -> int:
    """Increment and return loop count."""
    count = get_loop_count() + 1
    LOOP_COUNTER_FILE.write_text(str(count))
    return count


def reset_loop_count():
    """Reset counter — call when user sends a new prompt."""
    if LOOP_COUNTER_FILE.exists():
        LOOP_COUNTER_FILE.unlink()


# ── Vault Scanner ────────────────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> dict:
    """Extract YAML-style frontmatter from markdown file."""
    meta = {}
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return meta
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip().lower()] = val.strip()
    return meta


def check_stop_flag() -> bool:
    """Check if STOP.md exists — halt all autonomous actions."""
    stop_file = VAULT_PATH / "STOP.md"
    return stop_file.exists()


def find_auto_execute_tasks() -> list[dict]:
    """Find Needs_Action items with auto_execute: true."""
    tasks = []
    if not NEEDS_ACTION.exists():
        return tasks

    for f in sorted(NEEDS_ACTION.glob("*.md")):
        if f.name == ".gitkeep":
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            meta = parse_frontmatter(content)
            if meta.get("auto_execute", "").lower() == "true":
                tasks.append({
                    "file": f.name,
                    "path": str(f),
                    "subject": meta.get("subject", f.stem),
                    "type": meta.get("type", "task"),
                    "priority": meta.get("priority", "normal"),
                })
        except Exception:
            pass
    return tasks


def find_approved_items() -> list[dict]:
    """Find Approved/ items that haven't been processed yet."""
    items = []
    if not APPROVED.exists():
        return items

    for f in sorted(APPROVED.glob("*.md")):
        if f.name == ".gitkeep":
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            meta = parse_frontmatter(content)
            status = meta.get("status", "")
            item_type = meta.get("type", "")

            # Skip already-processed items (social posts handled by watchers)
            if item_type in ("linkedin_post", "facebook_post"):
                continue
            # Only pick up items marked for auto-execution
            if meta.get("auto_execute", "").lower() == "true":
                items.append({
                    "file": f.name,
                    "path": str(f),
                    "subject": meta.get("subject", f.stem),
                    "type": item_type,
                })
        except Exception:
            pass
    return items


def find_chained_tasks() -> list[dict]:
    """
    Find recently-completed items that have a next_action: field.
    Creates the next task automatically.
    """
    chains = []
    if not DONE.exists():
        return chains

    today = datetime.now().strftime("%Y-%m-%d")

    for f in sorted(DONE.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            meta = parse_frontmatter(content)

            next_action = meta.get("next_action", "").strip()
            chain_queued = meta.get("chain_queued", "").lower()

            # Only process if:
            # 1. Has a next_action
            # 2. Not already queued
            # 3. Completed today
            completed_date = meta.get("completed", meta.get("done_date", ""))
            if (next_action
                    and chain_queued != "true"
                    and today in completed_date):
                chains.append({
                    "source_file": f.name,
                    "source_path": str(f),
                    "next_action": next_action,
                    "subject": meta.get("subject", f.stem),
                })
        except Exception:
            pass
    return chains


def queue_chained_task(chain: dict):
    """Create a Needs_Action file for a chained next task."""
    NEEDS_ACTION.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"CHAIN_{today}_{timestamp}.md"
    filepath = NEEDS_ACTION / filename

    content = f"""---
type: chained_task
subject: {chain['next_action']}
created: {datetime.now().isoformat()}
triggered_by: {chain['source_file']}
auto_execute: true
status: pending
priority: normal
---

# Chained Task

**Triggered by:** {chain['source_file']}
**Previous task:** {chain['subject']}

## Action Required

{chain['next_action']}

---
*Auto-created by Ralph Wiggum Loop — chained task*
"""
    filepath.write_text(content, encoding="utf-8")

    # Mark source as chain_queued so we don't duplicate
    source = Path(chain["source_path"])
    source_content = source.read_text(encoding="utf-8")
    source_content = source_content.replace(
        "---\n",
        "---\nchain_queued: true\n",
        1  # Only first occurrence (frontmatter)
    )
    source.write_text(source_content, encoding="utf-8")

    return filename


def log_ralph_action(action: str, details: str):
    """Log Ralph loop actions."""
    today = datetime.now().strftime("%Y-%m-%d")
    LOGS.mkdir(parents=True, exist_ok=True)
    entry = f"[{datetime.now().isoformat()}] [RalphLoop] {action}: {details}\n"
    with open(LOGS / f"{today}.log", "a", encoding="utf-8") as f:
        f.write(entry)


# ── Main Hook Logic ───────────────────────────────────────────────────────────────

def main():
    # Emergency stop check
    if check_stop_flag():
        print(json.dumps({"decision": "block",
                          "reason": "RALPH: STOP.md detected — halting all autonomous actions."}))
        return

    # Check loop count — prevent runaway loops
    loop_count = get_loop_count()
    if loop_count >= MAX_LOOP_COUNT:
        # Reset for next session
        reset_loop_count()
        log_ralph_action("LOOP_LIMIT", f"Reached max loops ({MAX_LOOP_COUNT}) — stopping")
        sys.exit(0)  # Let Claude stop normally

    # ── Check for chained tasks ─────────────────────────────────────────────────
    chains = find_chained_tasks()
    if chains:
        for chain in chains:
            new_file = queue_chained_task(chain)
            log_ralph_action("CHAIN_QUEUED", f"{chain['source_file']} → {new_file}")

        count = increment_loop_count()
        task_list = "\n".join(f"- {c['next_action']}" for c in chains)
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"RALPH LOOP (iteration {count}/{MAX_LOOP_COUNT}): "
                f"Chained tasks queued from completed items:\n{task_list}\n\n"
                f"Please process these new tasks in Needs_Action/."
            )
        }))
        return

    # ── Check for auto-execute tasks ────────────────────────────────────────────
    auto_tasks = find_auto_execute_tasks()
    if auto_tasks:
        count = increment_loop_count()
        task_list = "\n".join(
            f"- [{t['type']}] {t['subject']} ({t['file']})"
            for t in auto_tasks[:5]
        )
        log_ralph_action("AUTO_EXECUTE", f"{len(auto_tasks)} tasks found")
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"RALPH LOOP (iteration {count}/{MAX_LOOP_COUNT}): "
                f"Found {len(auto_tasks)} task(s) with auto_execute: true:\n\n"
                f"{task_list}\n\n"
                f"Process each one: read the file, take the action, move to Done/."
            )
        }))
        return

    # ── Check for approved items needing execution ──────────────────────────────
    approved = find_approved_items()
    if approved:
        count = increment_loop_count()
        item_list = "\n".join(
            f"- [{a['type']}] {a['subject']} ({a['file']})"
            for a in approved[:5]
        )
        log_ralph_action("APPROVED_PENDING", f"{len(approved)} items found")
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"RALPH LOOP (iteration {count}/{MAX_LOOP_COUNT}): "
                f"Found {len(approved)} approved item(s) waiting for execution:\n\n"
                f"{item_list}\n\n"
                f"Execute each approved action and move to Done/."
            )
        }))
        return

    # ── Nothing to do — let Claude stop ─────────────────────────────────────────
    reset_loop_count()
    log_ralph_action("IDLE", "No pending tasks — Claude stopping normally")
    sys.exit(0)


if __name__ == "__main__":
    main()
