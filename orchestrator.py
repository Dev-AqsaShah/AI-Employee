"""
orchestrator.py — Master process for the AI Employee (Gold Tier)

Manages all watchers, handles scheduling, and monitors process health.

Usage:
    python orchestrator.py [--dry-run]

What it does:
  1. Starts filesystem_watcher in a subprocess
  2. Starts gmail_watcher in a subprocess (if credentials exist)
  3. Starts linkedin_watcher in a subprocess (if LINKEDIN_EMAIL set)
  4. Starts email_watcher in a subprocess (if EMAIL_FROM set)
  5. Starts facebook_watcher in a subprocess (if FB_PAGE_ID set)
  6. Runs a daily briefing at the configured time
  7. Runs LinkedIn + Facebook post schedulers after briefing
  8. Monitors all subprocesses and restarts on crash
  9. Checks for STOP.md to halt all operations
"""

import os
import sys
import time
import signal
import logging
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ─────────────────────────────────────────────────────────────────────
VAULT_PATH     = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
VENV_PYTHON    = Path(".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python")
BRIEFING_HOUR  = int(os.getenv("BRIEFING_HOUR", "8"))   # 8 AM daily briefing
DRY_RUN        = os.getenv("DRY_RUN", "false").lower() == "true"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Orchestrator] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Orchestrator")


def get_python() -> str:
    """Return path to Python executable (venv or system)."""
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


def log_event(event_type: str, details: str):
    today = datetime.now().strftime("%Y-%m-%d")
    logs_dir = VAULT_PATH / "Logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    entry = f"[{datetime.now(timezone.utc).isoformat()}] [Orchestrator] {event_type}: {details}\n"
    with open(logs_dir / f"{today}.log", "a") as f:
        f.write(entry)


# ── Process Manager ────────────────────────────────────────────────────────────

class ManagedProcess:
    """A subprocess that auto-restarts on crash."""

    def __init__(self, name: str, cmd: list, enabled: bool = True):
        self.name    = name
        self.cmd     = cmd
        self.enabled = enabled
        self.proc: Optional[subprocess.Popen] = None
        self.restart_count = 0

    def start(self):
        if not self.enabled:
            logger.info(f"{self.name}: disabled — skipping")
            return

        logger.info(f"Starting {self.name}: {' '.join(self.cmd)}")
        self.proc = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        log_event("PROCESS_START", f"{self.name} pid={self.proc.pid}")

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def restart(self):
        self.restart_count += 1
        logger.warning(f"Restarting {self.name} (restart #{self.restart_count})")
        log_event("PROCESS_RESTART", f"{self.name} restart_count={self.restart_count}")
        self.start()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            logger.info(f"Stopped {self.name}")
            log_event("PROCESS_STOP", self.name)


# ── Scheduler ──────────────────────────────────────────────────────────────────

class DailyScheduler(threading.Thread):
    """Runs the daily briefing at BRIEFING_HOUR every day."""

    def __init__(self, python_path: str):
        super().__init__(daemon=True)
        self.python     = python_path
        self._last_run  = None
        self._stop_flag = threading.Event()

    def stop(self):
        self._stop_flag.set()

    def run(self):
        logger.info(f"Scheduler started — daily briefing at {BRIEFING_HOUR:02d}:00")
        while not self._stop_flag.is_set():
            now = datetime.now()
            today = now.date()

            if now.hour == BRIEFING_HOUR and self._last_run != today:
                self._run_briefing()
                self._last_run = today

            self._stop_flag.wait(timeout=60)  # Check every minute

    def _run_briefing(self):
        logger.info("Running scheduled daily briefing...")
        log_event("BRIEFING_START", f"hour={BRIEFING_HOUR}")
        try:
            result = subprocess.run(
                [self.python, "run_process_inbox.py"],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                logger.info("Daily briefing complete.")
                log_event("BRIEFING_DONE", "success")
            else:
                logger.error(f"Briefing failed: {result.stderr[:200]}")
                log_event("BRIEFING_ERROR", result.stderr[:200])
        except Exception as e:
            logger.error(f"Briefing exception: {e}")
            log_event("BRIEFING_EXCEPTION", str(e))

        # Run content schedulers after briefing
        self._run_linkedin_scheduler()
        self._run_facebook_scheduler()

    def _run_linkedin_scheduler(self):
        logger.info("Running LinkedIn post scheduler...")
        try:
            result = subprocess.run(
                [self.python, "schedulers/linkedin_scheduler.py"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                logger.info("LinkedIn scheduler complete.")
                log_event("LINKEDIN_SCHEDULER_DONE", result.stdout.strip()[:200])
            else:
                logger.warning(f"LinkedIn scheduler: {result.stderr[:200]}")
        except Exception as e:
            logger.error(f"LinkedIn scheduler exception: {e}")
            log_event("LINKEDIN_SCHEDULER_ERROR", str(e))

    def _run_facebook_scheduler(self):
        logger.info("Running Facebook post scheduler...")
        fb_page_id = os.getenv("FACEBOOK_EMAIL", "")
        if not fb_page_id:
            logger.info("Facebook scheduler: FACEBOOK_EMAIL not set — skipping")
            return
        try:
            result = subprocess.run(
                [self.python, "schedulers/facebook_scheduler.py"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                logger.info("Facebook scheduler complete.")
                log_event("FACEBOOK_SCHEDULER_DONE", result.stdout.strip()[:200])
            else:
                logger.warning(f"Facebook scheduler: {result.stderr[:200]}")
        except Exception as e:
            logger.error(f"Facebook scheduler exception: {e}")
            log_event("FACEBOOK_SCHEDULER_ERROR", str(e))


# ── Main Orchestrator ──────────────────────────────────────────────────────────

class Orchestrator:
    def __init__(self):
        self.python    = get_python()
        self.stop_file = VAULT_PATH / "STOP.md"
        self.processes: list[ManagedProcess] = []
        self.scheduler: Optional[DailyScheduler] = None
        self._running  = False

    def _build_processes(self) -> list[ManagedProcess]:
        python = self.python
        processes = []

        # Filesystem watcher — always enabled
        processes.append(ManagedProcess(
            name="filesystem-watcher",
            cmd=[python, "watchers/filesystem_watcher.py"],
            enabled=True,
        ))

        # Gmail watcher — enabled if credentials exist
        gmail_creds = Path("credentials/gmail_credentials.json")
        processes.append(ManagedProcess(
            name="gmail-watcher",
            cmd=[python, "watchers/gmail_watcher.py"],
            enabled=gmail_creds.exists(),
        ))

        # LinkedIn watcher — enabled if credentials configured
        linkedin_email = os.getenv("LINKEDIN_EMAIL", "")
        processes.append(ManagedProcess(
            name="linkedin-watcher",
            cmd=[python, "watchers/linkedin_watcher.py"],
            enabled=bool(linkedin_email),
        ))

        # Email watcher — enabled if SMTP credentials configured
        email_from = os.getenv("EMAIL_FROM", "")
        processes.append(ManagedProcess(
            name="email-watcher",
            cmd=[python, "watchers/email_watcher.py"],
            enabled=bool(email_from),
        ))

        # Facebook watcher — enabled if FACEBOOK_EMAIL configured
        fb_email = os.getenv("FACEBOOK_EMAIL", "")
        processes.append(ManagedProcess(
            name="facebook-watcher",
            cmd=[python, "watchers/facebook_watcher.py"],
            enabled=bool(fb_email),
        ))

        return processes

    def start(self):
        logger.info("=" * 50)
        logger.info("AI Employee Orchestrator starting (Gold Tier)")
        logger.info(f"Vault: {VAULT_PATH.resolve()}")
        logger.info(f"Python: {self.python}")
        logger.info(f"Daily briefing at: {BRIEFING_HOUR:02d}:00")
        if DRY_RUN:
            logger.info("[DRY RUN MODE]")
        logger.info("=" * 50)

        self.processes = self._build_processes()
        for proc in self.processes:
            proc.start()
            time.sleep(1)  # Stagger starts

        self.scheduler = DailyScheduler(self.python)
        self.scheduler.start()

        self._running = True
        log_event("ORCHESTRATOR_START", f"processes={len([p for p in self.processes if p.enabled])}")

    def stop(self, signum=None, frame=None):
        logger.info("Stopping orchestrator...")
        self._running = False
        if self.scheduler:
            self.scheduler.stop()
        for proc in self.processes:
            proc.stop()
        log_event("ORCHESTRATOR_STOP", "graceful")
        sys.exit(0)

    def run(self):
        self.start()

        # Handle Ctrl+C
        signal.signal(signal.SIGINT,  self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        logger.info("Orchestrator running. Press Ctrl+C to stop.")

        while self._running:
            # Emergency stop check
            if self.stop_file.exists():
                logger.warning("STOP.md detected — halting all processes.")
                self.stop()

            # Health check + restart crashed processes
            for proc in self.processes:
                if proc.enabled and not proc.is_running():
                    proc.restart()
                    time.sleep(2)

            time.sleep(10)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI Employee Orchestrator")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    orc = Orchestrator()
    orc.run()


if __name__ == "__main__":
    main()
