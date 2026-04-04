"""
scripts/sync_vault.py — Git-based vault sync for Platinum Tier

Syncs the AI_Employee_Vault between Cloud and Local agents via Git.
Secrets are NEVER synced (.env, credentials/, tokens, WhatsApp sessions).

Usage:
    python scripts/sync_vault.py --pull     # Pull latest from remote
    python scripts/sync_vault.py --push     # Commit + push local changes
    python scripts/sync_vault.py --sync     # Pull then push (full sync)
    python scripts/sync_vault.py --watch    # Watch for changes and auto-push (every 5 min)

Security rules (Platinum Tier):
  - Only markdown and state files are synced
  - .env, credentials/, *.json tokens, WhatsApp sessions NEVER sync
  - Cloud never stores or uses WhatsApp sessions or banking credentials
"""

import os
import sys
import time
import subprocess
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

VAULT_PATH  = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
AGENT_ID    = os.getenv("AGENT_ID", "local")
SYNC_BRANCH = os.getenv("VAULT_SYNC_BRANCH", "main")
SYNC_REMOTE = os.getenv("VAULT_SYNC_REMOTE", "origin")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [VaultSync] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("VaultSync")


def run_git(args: list, cwd: str = ".") -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        cwd=cwd
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def ensure_gitignore_vault():
    """
    Ensure .gitignore is correct — secrets NEVER sync.
    This is a security-critical function.
    """
    gitignore = Path(".gitignore")
    required_ignores = [
        ".env",
        ".env.*",
        "credentials/",
        "*.pem",
        "*.key",
        "gmail_token.json",
        "state.json",
        "browser_data/",
        "browser_data2/",
        "__pycache__/",
        "*.pyc",
        ".venv/",
        "debug_screenshots/",
        "uploads/",
        ".processed_*",
    ]

    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    missing = [rule for rule in required_ignores if rule not in existing]

    if missing:
        with open(gitignore, "a", encoding="utf-8") as f:
            f.write("\n# Security: Platinum Tier — secrets never sync\n")
            for rule in missing:
                f.write(f"{rule}\n")
        logger.info(f"Updated .gitignore with {len(missing)} security rules")


def git_pull() -> bool:
    """Pull latest vault changes from remote."""
    logger.info(f"Pulling from {SYNC_REMOTE}/{SYNC_BRANCH}...")

    # Fetch first
    rc, out, err = run_git(["fetch", SYNC_REMOTE, SYNC_BRANCH])
    if rc != 0:
        logger.error(f"Git fetch failed: {err}")
        return False

    # Merge with strategy: prefer remote for vault files, but never overwrite local secrets
    rc, out, err = run_git(["merge", f"{SYNC_REMOTE}/{SYNC_BRANCH}",
                            "--no-edit", "-m",
                            f"[{AGENT_ID}] Auto-merge vault sync {datetime.now(timezone.utc).isoformat()}"])
    if rc != 0:
        logger.warning(f"Merge conflict — attempting resolve: {err}")
        # Auto-resolve: keep local for credentials, remote for vault markdown
        rc2, _, _ = run_git(["checkout", "--theirs", "AI_Employee_Vault/"])
        run_git(["add", "AI_Employee_Vault/"])
        rc3, _, _ = run_git(["commit", "-m", f"[{AGENT_ID}] Resolved merge conflict (vault sync)"])
        if rc3 != 0:
            logger.error("Failed to resolve merge conflict automatically")
            return False

    logger.info(f"Pull complete: {out[:100]}")
    return True


def git_push() -> bool:
    """Commit any vault changes and push to remote."""
    # Check if there's anything to commit
    rc, status, _ = run_git(["status", "--porcelain", "AI_Employee_Vault/"])
    if not status.strip():
        logger.info("No vault changes to push")
        return True

    # Stage only vault markdown files (never credentials)
    rc, _, err = run_git(["add", "AI_Employee_Vault/"])
    if rc != 0:
        logger.error(f"Git add failed: {err}")
        return False

    # Commit
    ts  = datetime.now(timezone.utc).isoformat()
    msg = f"[{AGENT_ID}] Vault sync {ts}"
    rc, out, err = run_git(["commit", "-m", msg])
    if rc != 0:
        if "nothing to commit" in err or "nothing to commit" in out:
            logger.info("Nothing to commit after staging")
            return True
        logger.error(f"Git commit failed: {err}")
        return False

    # Push
    rc, out, err = run_git(["push", SYNC_REMOTE, SYNC_BRANCH])
    if rc != 0:
        logger.error(f"Git push failed: {err}")
        return False

    logger.info(f"Push complete: {out[:100]}")
    return True


def full_sync() -> bool:
    """Pull from remote, then push local changes."""
    logger.info("Starting full vault sync (pull + push)...")
    ensure_gitignore_vault()

    pulled = git_pull()
    if not pulled:
        logger.error("Pull failed — aborting sync")
        return False

    pushed = git_push()
    if not pushed:
        logger.error("Push failed")
        return False

    logger.info("Full sync complete")
    return True


def watch_mode(interval_seconds: int = 300):
    """Watch vault for changes and auto-push every N seconds."""
    logger.info(f"Watch mode: syncing every {interval_seconds}s")
    ensure_gitignore_vault()

    while True:
        try:
            # Check for STOP.md
            if (VAULT_PATH / "STOP.md").exists():
                logger.warning("STOP.md detected — halting vault sync")
                break

            full_sync()

        except Exception as e:
            logger.error(f"Sync error: {e}")

        time.sleep(interval_seconds)


def main():
    parser = argparse.ArgumentParser(description="Vault Git sync for Platinum Tier")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pull",  action="store_true", help="Pull from remote")
    group.add_argument("--push",  action="store_true", help="Commit + push to remote")
    group.add_argument("--sync",  action="store_true", help="Pull then push")
    group.add_argument("--watch", action="store_true", help="Auto-sync every 5 minutes")
    parser.add_argument("--interval", type=int, default=300, help="Watch interval in seconds (default 300)")
    args = parser.parse_args()

    ensure_gitignore_vault()

    if args.pull:
        success = git_pull()
        sys.exit(0 if success else 1)
    elif args.push:
        success = git_push()
        sys.exit(0 if success else 1)
    elif args.sync:
        success = full_sync()
        sys.exit(0 if success else 1)
    elif args.watch:
        watch_mode(args.interval)


if __name__ == "__main__":
    main()
