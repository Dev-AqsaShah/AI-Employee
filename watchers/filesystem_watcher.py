"""
filesystem_watcher.py — Watches a drop folder for new files and creates
Needs_Action items in the Obsidian vault.

Usage:
    python filesystem_watcher.py [--vault PATH] [--drop PATH] [--dry-run]

Environment variables (override CLI flags):
    VAULT_PATH   — absolute path to AI_Employee_Vault
    DROP_PATH    — folder to watch for new files
    DRY_RUN      — set to 'true' to log actions without writing files
"""

import os
import sys
import argparse
import shutil
import time
from pathlib import Path
from datetime import datetime

# Allow running from repo root or watchers/ directory
sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


# ── DRY RUN GUARD ──────────────────────────────────────────────────────────────
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"


class DropFolderHandler(FileSystemEventHandler):
    """
    Watchdog event handler: when a file lands in the drop folder,
    copy it to the vault Inbox and create a Needs_Action .md file.
    """

    def __init__(self, watcher: "FilesystemWatcher"):
        super().__init__()
        self.watcher = watcher

    def on_created(self, event):
        if event.is_directory:
            return
        source = Path(event.src_path)
        # Give the file a moment to finish writing
        time.sleep(0.5)
        self.watcher.handle_new_file(source)


class FilesystemWatcher(BaseWatcher):
    """
    Monitors a local drop folder. When files appear, it:
      1. Copies the file to /Inbox/
      2. Creates a Needs_Action .md describing the file
    """

    def __init__(self, vault_path: str, drop_path: str, check_interval: int = 5):
        super().__init__(vault_path, check_interval=check_interval)
        self.drop_path = Path(drop_path).expanduser().resolve()
        self.inbox = self.vault_path / "Inbox"
        self.inbox.mkdir(parents=True, exist_ok=True)
        self.drop_path.mkdir(parents=True, exist_ok=True)
        self._seen: set = set()

    # ── BaseWatcher interface ──────────────────────────────────────────────────

    def check_for_updates(self) -> list:
        """Scan the drop folder for new files (polling fallback)."""
        new_files = []
        for f in self.drop_path.iterdir():
            if f.is_file() and f.name != ".gitkeep" and str(f) not in self._seen:
                new_files.append(f)
        return new_files

    def create_action_file(self, item: Path) -> Path:
        """Process a new file: copy to Inbox + write a Needs_Action md."""
        return self.handle_new_file(item)

    # ── Core logic ────────────────────────────────────────────────────────────

    def handle_new_file(self, source: Path) -> Path:
        """Copy source file to Inbox and generate a Needs_Action .md."""
        if str(source) in self._seen:
            return source  # Already processed
        self._seen.add(str(source))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = source.name.replace(" ", "_")
        inbox_dest = self.inbox / f"{timestamp}_{safe_name}"

        if DRY_RUN:
            self.logger.info(f"[DRY RUN] Would copy {source.name} → {inbox_dest}")
        else:
            shutil.copy2(source, inbox_dest)
            self.logger.info(f"Copied {source.name} → Inbox")

        # Create the Needs_Action markdown file
        action_path = self._write_action_md(source, inbox_dest, timestamp)

        # Move the original out of the drop folder (prevent re-processing)
        processed_dir = self.drop_path / "_processed"
        if not DRY_RUN:
            processed_dir.mkdir(exist_ok=True)
            shutil.move(str(source), str(processed_dir / source.name))

        return action_path

    def _write_action_md(self, source: Path, inbox_dest: Path, timestamp: str) -> Path:
        stat = source.stat() if source.exists() else None
        size = f"{stat.st_size:,} bytes" if stat else "unknown"
        suffix = source.suffix.lower()

        content = f"""---
type: file_drop
source_name: {source.name}
inbox_path: {inbox_dest.name}
size: {size}
extension: {suffix}
received: {datetime.now().isoformat()}
priority: normal
status: pending
---

## New File Received

A file has been dropped into the watch folder and is ready for processing.

| Field     | Value                |
|-----------|----------------------|
| Name      | `{source.name}`      |
| Size      | {size}               |
| Type      | `{suffix or 'unknown'}` |
| Received  | {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} |
| Inbox     | `Inbox/{inbox_dest.name}` |

## Suggested Actions
- [ ] Review the file contents
- [ ] Determine action required
- [ ] Move to /Done when complete

## Notes
_Add any notes about this file here._
"""
        action_filename = f"FILE_{timestamp}_{source.stem[:40]}.md"
        action_path = self.needs_action / action_filename

        if DRY_RUN:
            self.logger.info(f"[DRY RUN] Would create: {action_path}")
        else:
            action_path.write_text(content, encoding="utf-8")

        return action_path

    # ── Runner ────────────────────────────────────────────────────────────────

    def run(self):
        self.logger.info(f"Drop folder: {self.drop_path}")
        self.logger.info(f"Inbox:       {self.inbox}")
        if DRY_RUN:
            self.logger.info("[DRY RUN MODE] No files will be written.")

        if WATCHDOG_AVAILABLE:
            self._run_with_watchdog()
        else:
            self.logger.warning("watchdog not installed — falling back to polling mode")
            self._run_polling()

    def _run_with_watchdog(self):
        """Use watchdog for real-time event-driven watching."""
        handler = DropFolderHandler(self)
        observer = Observer()
        observer.schedule(handler, str(self.drop_path), recursive=False)
        observer.start()
        self.logger.info("Watchdog observer started (event-driven mode)")

        stop_file = self.vault_path / "STOP.md"
        try:
            while True:
                if stop_file.exists():
                    self.logger.warning("STOP.md detected — halting watcher.")
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Stopped by user.")
        finally:
            observer.stop()
            observer.join()

    def _run_polling(self):
        """Poll the drop folder every check_interval seconds."""
        stop_file = self.vault_path / "STOP.md"
        while True:
            if stop_file.exists():
                self.logger.warning("STOP.md detected — halting watcher.")
                time.sleep(10)
                continue
            try:
                items = self.check_for_updates()
                for item in items:
                    self.create_action_file(item)
            except KeyboardInterrupt:
                self.logger.info("Stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Polling error: {e}")
                self.log_event("ERROR", str(e))
            time.sleep(self.check_interval)


# ── CLI entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — Filesystem Watcher (Bronze Tier)"
    )
    parser.add_argument(
        "--vault",
        default=os.getenv("VAULT_PATH", str(Path(__file__).parent.parent / "AI_Employee_Vault")),
        help="Path to the Obsidian vault (default: ../AI_Employee_Vault)",
    )
    parser.add_argument(
        "--drop",
        default=os.getenv("DROP_PATH", str(Path(__file__).parent.parent / "drop_folder")),
        help="Folder to watch for new files (default: ../drop_folder)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Polling interval in seconds when watchdog is unavailable (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log actions without writing files",
    )
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
        global DRY_RUN
        DRY_RUN = True

    watcher = FilesystemWatcher(
        vault_path=args.vault,
        drop_path=args.drop,
        check_interval=args.interval,
    )
    watcher.run()


if __name__ == "__main__":
    main()
