"""
base_watcher.py — Abstract base class for all AI Employee watchers.

All watchers follow the same pattern:
  1. check_for_updates() — returns a list of new items
  2. create_action_file(item) — writes a .md file to /Needs_Action/
  3. run() — loops forever, sleeping between checks

Platinum Tier: Claim-by-move rule
  Before processing a Needs_Action item, call claim_item(path).
  This atomically moves the file to /In_Progress/<agent_id>/.
  If the move fails (another agent claimed it), skip it.
  Call release_item(path) when done (moves to Done or Pending_Approval).
"""

import os
import time
import logging
import sys
from pathlib import Path
from abc import ABC, abstractmethod
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)


class BaseWatcher(ABC):
    """Abstract base class for all AI Employee watchers."""

    def __init__(self, vault_path: str, check_interval: int = 60):
        self.vault_path   = Path(vault_path).expanduser().resolve()
        self.needs_action = self.vault_path / "Needs_Action"
        self.in_progress  = self.vault_path / "In_Progress"
        self.logs_dir     = self.vault_path / "Logs"
        self.check_interval = check_interval
        self.agent_id     = os.getenv("AGENT_ID", "local")
        self.logger       = logging.getLogger(self.__class__.__name__)
        self._ensure_dirs()

    def _ensure_dirs(self):
        """Make sure required vault directories exist."""
        self.needs_action.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        # Platinum Tier: In_Progress dirs for claim-by-move
        (self.in_progress / self.agent_id).mkdir(parents=True, exist_ok=True)

    # ── Claim-by-move (Platinum Tier) ─────────────────────────────────────

    def claim_item(self, source: Path) -> Path | None:
        """
        Atomically claim a Needs_Action item by moving it to
        /In_Progress/<agent_id>/. Returns the new path if claimed,
        or None if another agent already claimed it (file gone).

        This prevents double-processing between cloud and local agents.
        """
        dest = self.in_progress / self.agent_id / source.name
        try:
            source.rename(dest)
            self.logger.debug(f"Claimed: {source.name} -> In_Progress/{self.agent_id}/")
            self.log_event("CLAIMED", f"{source.name} by {self.agent_id}")
            return dest
        except (FileNotFoundError, OSError):
            # File already moved by another agent — skip it
            self.logger.debug(f"Already claimed by another agent: {source.name}")
            return None

    def release_item(self, claimed_path: Path, dest_folder: Path):
        """
        Move a claimed item from In_Progress to its final destination
        (Done, Pending_Approval, etc.).
        """
        dest_folder.mkdir(parents=True, exist_ok=True)
        dest = dest_folder / claimed_path.name
        try:
            claimed_path.rename(dest)
            self.log_event("RELEASED", f"{claimed_path.name} -> {dest_folder.name}/")
        except Exception as e:
            self.logger.error(f"Failed to release {claimed_path.name}: {e}")

    @abstractmethod
    def check_for_updates(self) -> list:
        """Return a list of new items to process."""
        pass

    @abstractmethod
    def create_action_file(self, item) -> Path:
        """Create a .md file in Needs_Action/ for this item."""
        pass

    def log_event(self, event_type: str, details: str):
        """Append a log entry to today's log file."""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.logs_dir / f"{today}.log"
        entry = f"[{datetime.now().isoformat()}] [{self.__class__.__name__}] {event_type}: {details}\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry)

    def run(self):
        """Main watcher loop — runs indefinitely."""
        self.logger.info(f"Starting {self.__class__.__name__} (vault: {self.vault_path})")
        self.logger.info(f"Check interval: {self.check_interval}s")

        # Check for emergency stop file
        stop_file = self.vault_path / "STOP.md"

        while True:
            # Emergency stop check
            if stop_file.exists():
                self.logger.warning("STOP.md detected — halting watcher. Remove STOP.md to resume.")
                time.sleep(10)
                continue

            try:
                items = self.check_for_updates()
                for item in items:
                    path = self.create_action_file(item)
                    self.logger.info(f"Created action file: {path.name}")
                    self.log_event("ACTION_CREATED", str(path.name))
            except KeyboardInterrupt:
                self.logger.info("Watcher stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Error in check loop: {e}")
                self.log_event("ERROR", str(e))

            time.sleep(self.check_interval)
