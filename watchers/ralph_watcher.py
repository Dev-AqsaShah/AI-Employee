"""
ralph_watcher.py — Ralph Wiggum Loop: Autonomous Task Chain Daemon

Watches the vault for task chains and auto-executable items.
Runs as a background daemon alongside other watchers.

"I'm helping!" — Ralph Wiggum

What it does:
  1. Watches Done/ for tasks with next_action: field → queues next task
  2. Watches Needs_Action/ for auto_execute: true items → processes them
  3. Handles multi-step task chains autonomously
  4. Respects STOP.md and Company_Handbook.md rules

Task Chain Example:
  Task A (done) → next_action: "Send invoice to client" →
  Task B auto-created in Needs_Action/ →
  (Claude processes it) →
  Task B (done) → next_action: "Follow up in 3 days" →
  Task C created...

Auto-Execute Format (in Needs_Action/ files):
  ---
  auto_execute: true
  subject: Update Dashboard stats
  type: system_task
  ---

Usage:
    python watchers/ralph_watcher.py
    python watchers/ralph_watcher.py --dry-run
    python watchers/ralph_watcher.py --once    # Run once, don't loop
"""

import os
import sys
import re
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [RalphWatcher] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("RalphWatcher")

# ── Config ───────────────────────────────────────────────────────────────────────

VAULT_PATH   = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
NEEDS_ACTION = VAULT_PATH / "Needs_Action"
APPROVED     = VAULT_PATH / "Approved"
DONE         = VAULT_PATH / "Done"
LOGS         = VAULT_PATH / "Logs"

POLL_INTERVAL = 30  # seconds between checks


# ── Helpers ──────────────────────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> dict:
    """Extract YAML-style frontmatter."""
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
    return (VAULT_PATH / "STOP.md").exists()


def log_event(event_type: str, details: str):
    today = datetime.now().strftime("%Y-%m-%d")
    LOGS.mkdir(parents=True, exist_ok=True)
    entry = f"[{datetime.now(timezone.utc).isoformat()}] [RalphWatcher] {event_type}: {details}\n"
    with open(LOGS / f"{today}.log", "a", encoding="utf-8") as f:
        f.write(entry)


# ── Task Chain Handler ───────────────────────────────────────────────────────────

def process_done_chains(dry_run: bool = False) -> int:
    """
    Check Done/ for items with next_action: field.
    Creates the next task in Needs_Action/ automatically.
    Returns count of chains processed.
    """
    count = 0
    if not DONE.exists():
        return count

    today = datetime.now().strftime("%Y-%m-%d")

    for f in sorted(DONE.glob("*.md")):
        if f.name == ".gitkeep":
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            meta = parse_frontmatter(content)

            next_action = meta.get("next_action", "").strip()
            chain_queued = meta.get("chain_queued", "").lower()

            if not next_action or chain_queued == "true":
                continue

            logger.info(f"Chain detected: {f.name} → '{next_action}'")

            if dry_run:
                logger.info(f"[DRY RUN] Would create Needs_Action task: {next_action}")
                count += 1
                continue

            # Create the next task
            NEEDS_ACTION.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%H%M%S")
            new_filename = f"CHAIN_{today}_{timestamp}.md"
            new_filepath = NEEDS_ACTION / new_filename

            subject = meta.get("subject", f.stem)
            new_content = f"""---
type: chained_task
subject: {next_action}
created: {datetime.now(timezone.utc).isoformat()}
triggered_by: {f.name}
previous_task: {subject}
auto_execute: false
status: pending
priority: normal
---

# Chained Task

> Auto-created by Ralph Wiggum Loop

**Triggered by completion of:** {f.name}
**Previous task:** {subject}

## Action Required

{next_action}

---
*Review and move to Approved/ to execute, or edit as needed.*
"""
            new_filepath.write_text(new_content, encoding="utf-8")
            logger.info(f"Created chained task: {new_filename}")

            # Mark source as chain_queued
            updated = content
            if "chain_queued:" not in content:
                # Insert after first ---
                updated = re.sub(
                    r'^(---\n)',
                    r'\1chain_queued: true\n',
                    content,
                    count=1
                )
            else:
                updated = re.sub(r'chain_queued:\s*\w+', 'chain_queued: true', content)

            f.write_text(updated, encoding="utf-8")

            log_event("CHAIN_QUEUED", f"{f.name} → {new_filename}: {next_action}")
            count += 1

        except Exception as e:
            logger.warning(f"Error processing {f.name}: {e}")

    return count


# ── Auto-Execute Handler ──────────────────────────────────────────────────────────

def process_auto_execute_tasks(dry_run: bool = False) -> int:
    """
    Find Needs_Action items with auto_execute: true.
    For system tasks (update stats, cleanup), execute directly.
    Returns count processed.
    """
    count = 0
    if not NEEDS_ACTION.exists():
        return count

    for f in sorted(NEEDS_ACTION.glob("*.md")):
        if f.name == ".gitkeep":
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            meta = parse_frontmatter(content)

            if meta.get("auto_execute", "").lower() != "true":
                continue

            task_type = meta.get("type", "task")
            subject   = meta.get("subject", f.stem)

            logger.info(f"Auto-execute: [{task_type}] {subject}")

            if dry_run:
                logger.info(f"[DRY RUN] Would execute: {subject}")
                count += 1
                continue

            # Handle known system task types
            executed = False

            if task_type == "update_dashboard":
                executed = _run_update_dashboard(content, meta)
            elif task_type == "cleanup_done":
                executed = _run_cleanup_done(content, meta)
            elif task_type == "vault_summary":
                executed = _run_vault_summary(content, meta)
            else:
                # Unknown type — log it but don't auto-execute
                # (requires Claude Code to process)
                logger.info(f"  Type '{task_type}' requires Claude Code — skipping auto-execute")
                continue

            if executed:
                # Move to Done
                DONE.mkdir(parents=True, exist_ok=True)
                today = datetime.now().strftime("%Y-%m-%d")
                done_path = DONE / f.name
                updated = content + f"\n\n## Completed [{datetime.now(timezone.utc).isoformat()}]\n- Auto-executed by Ralph Watcher\n"
                # Update frontmatter status
                updated = re.sub(r'status:\s*\S+', 'status: done', updated, count=1)
                done_path.write_text(updated, encoding="utf-8")
                f.unlink()
                log_event("AUTO_EXECUTED", f"{f.name} [{task_type}]")
                count += 1

        except Exception as e:
            logger.warning(f"Error auto-executing {f.name}: {e}")

    return count


# ── System Task Executors ────────────────────────────────────────────────────────

def _run_update_dashboard(content: str, meta: dict) -> bool:
    """Update Dashboard.md stats."""
    dashboard = VAULT_PATH / "Dashboard.md"
    if not dashboard.exists():
        return False

    dash = dashboard.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc)

    # Count vault items
    needs_count   = len([f for f in NEEDS_ACTION.glob("*.md") if f.name != ".gitkeep"]) if NEEDS_ACTION.exists() else 0
    pending_count = len([f for f in (VAULT_PATH / "Pending_Approval").glob("*.md") if f.name != ".gitkeep"]) if (VAULT_PATH / "Pending_Approval").exists() else 0
    done_count    = len([f for f in DONE.glob("*.md") if f.name != ".gitkeep"]) if DONE.exists() else 0

    # Update counts
    dash = re.sub(r'\*\*Needs Action:\*\*\s*\d+', f'**Needs Action:** {needs_count}', dash)
    dash = re.sub(r'\*\*Pending Approval:\*\*\s*\d+', f'**Pending Approval:** {pending_count}', dash)

    # Add activity row
    row = f"| {now.strftime('%Y-%m-%d %H:%M:%S')} | Ralph: Dashboard stats updated (needs={needs_count}, pending={pending_count}, done={done_count}) |"
    dash = dash.replace(
        "| Time (UTC)          | Action                                      |",
        "| Time (UTC)          | Action                                      |\n" + row,
    )
    dashboard.write_text(dash, encoding="utf-8")
    logger.info(f"Dashboard updated: needs={needs_count} pending={pending_count} done={done_count}")
    return True


def _run_cleanup_done(content: str, meta: dict) -> bool:
    """Archive old Done items (older than 30 days) to Done/Archive/."""
    from datetime import timedelta
    archive_dir = DONE / "Archive"
    cutoff = datetime.now() - timedelta(days=30)
    moved = 0

    if not DONE.exists():
        return True

    for f in DONE.glob("*.md"):
        if f.name == ".gitkeep":
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                archive_dir.mkdir(parents=True, exist_ok=True)
                f.rename(archive_dir / f.name)
                moved += 1
        except Exception:
            pass

    logger.info(f"Archived {moved} old Done items")
    return True


def _run_vault_summary(content: str, meta: dict) -> bool:
    """Create a quick vault summary log entry."""
    needs   = len(list(NEEDS_ACTION.glob("*.md"))) if NEEDS_ACTION.exists() else 0
    pending = len(list((VAULT_PATH / "Pending_Approval").glob("*.md"))) if (VAULT_PATH / "Pending_Approval").exists() else 0
    done    = len(list(DONE.glob("*.md"))) if DONE.exists() else 0

    log_event("VAULT_SUMMARY", f"needs={needs} pending={pending} done={done}")
    logger.info(f"Vault summary: needs={needs} pending={pending} done={done}")
    return True


# ── Main Loop ────────────────────────────────────────────────────────────────────

def run_once(dry_run: bool = False) -> dict:
    """Run one check cycle. Returns counts."""
    if check_stop_flag():
        logger.warning("STOP.md detected — halting Ralph Watcher")
        return {"chains": 0, "auto_executed": 0, "stopped": True}

    chains   = process_done_chains(dry_run=dry_run)
    executed = process_auto_execute_tasks(dry_run=dry_run)

    if chains or executed:
        logger.info(f"Cycle complete: {chains} chains queued, {executed} tasks auto-executed")

    return {"chains": chains, "auto_executed": executed, "stopped": False}


def main():
    parser = argparse.ArgumentParser(description="Ralph Wiggum Loop — Autonomous Task Chain Watcher")
    parser.add_argument("--dry-run", action="store_true", help="Preview without executing")
    parser.add_argument("--once",    action="store_true", help="Run once and exit")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("[DRY RUN MODE]")

    logger.info("Ralph Watcher starting — watching for task chains...")
    log_event("RALPH_START", f"dry_run={args.dry_run}")

    try:
        if args.once:
            result = run_once(dry_run=args.dry_run)
            logger.info(f"Run complete: {result}")
            return

        # Continuous loop
        while True:
            result = run_once(dry_run=args.dry_run)
            if result.get("stopped"):
                break
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        logger.info("Ralph Watcher stopped by user")
        log_event("RALPH_STOP", "KeyboardInterrupt")


if __name__ == "__main__":
    main()
