"""
cloud_orchestrator.py — Platinum Tier Cloud Agent

Runs on Oracle/AWS cloud VM 24/7.
Cloud owns: Gmail triage, email draft replies, social post DRAFTS (pending approval only).
Cloud does NOT: send/post anything, touch WhatsApp, payments, banking.

Usage:
    python cloud_orchestrator.py [--dry-run]

Work-Zone Specialization (Platinum Tier):
  Cloud owns  → Email triage, draft replies, social post drafts/scheduling
  Local owns  → Approvals, WhatsApp, payments, final send/post actions

Communication via vault (Git-synced):
  Cloud writes → /Needs_Action/cloud/, /Plans/cloud/, /Pending_Approval/cloud/
  Cloud writes → /Updates/<timestamp>.md  (status updates for Local)
  Local reads  → /Updates/ and merges into Dashboard.md
  Local writes → /Signals/<timestamp>.md  (commands to Cloud)
  Cloud reads  → /Signals/ for directives from Local

Claim-by-move rule:
  Before processing any item in /Needs_Action, move it to
  /In_Progress/<agent_id>/ first. If move fails, another agent
  claimed it — skip it.
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
VAULT_PATH    = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
AGENT_ID      = os.getenv("AGENT_ID", "cloud")          # "cloud" or "local"
BRIEFING_HOUR = int(os.getenv("BRIEFING_HOUR", "8"))
DRY_RUN       = os.getenv("DRY_RUN", "false").lower() == "true"

# Cloud runs venv python
VENV_PYTHON = Path(".venv/bin/python")  # Linux cloud VM uses bin/ not Scripts/

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CloudOrchestrator] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("CloudOrchestrator")


def get_python() -> str:
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


def log_event(event_type: str, details: str):
    today = datetime.now().strftime("%Y-%m-%d")
    logs_dir = VAULT_PATH / "Logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    entry = f"[{datetime.now(timezone.utc).isoformat()}] [CloudOrchestrator] {event_type}: {details}\n"
    with open(logs_dir / f"{today}.log", "a") as f:
        f.write(entry)


def write_update(message: str):
    """Write a status update file for Local agent to merge into Dashboard."""
    updates_dir = VAULT_PATH / "Updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = updates_dir / f"UPDATE_{ts}.md"
    path.write_text(
        f"---\nagent: cloud\ntimestamp: {datetime.now(timezone.utc).isoformat()}\n---\n\n{message}\n",
        encoding="utf-8"
    )
    logger.info(f"Update written: {path.name}")


def read_signals() -> list:
    """Read command signals from Local agent."""
    signals_dir = VAULT_PATH / "Signals"
    signals_dir.mkdir(parents=True, exist_ok=True)
    signals = []
    for f in signals_dir.iterdir():
        if f.suffix == ".md" and f.name != ".gitkeep":
            content = f.read_text(encoding="utf-8", errors="ignore")
            signals.append({"file": f, "content": content})
    return signals


# ── Process Manager (reuse same pattern as local orchestrator) ─────────────────

class ManagedProcess:
    MAX_BACKOFF  = 300
    MAX_RESTARTS = 20

    def __init__(self, name: str, cmd: list, enabled: bool = True):
        self.name    = name
        self.cmd     = cmd
        self.enabled = enabled
        self.proc: Optional[subprocess.Popen] = None
        self.restart_count = 0
        self._next_restart_at: float = 0.0

    def start(self):
        if not self.enabled:
            logger.info(f"{self.name}: disabled")
            return
        logger.info(f"Starting {self.name}")
        self.proc = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        log_event("PROCESS_START", f"{self.name} pid={self.proc.pid}")

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def needs_restart(self) -> bool:
        if not self.enabled or self.is_running():
            return False
        if self.restart_count >= self.MAX_RESTARTS:
            return False
        return time.time() >= self._next_restart_at

    def restart(self):
        self.restart_count += 1
        backoff = min(30 * (2 ** (self.restart_count - 1)), self.MAX_BACKOFF)
        self._next_restart_at = time.time() + backoff
        logger.warning(f"Restarting {self.name} (#{self.restart_count}, backoff={backoff}s)")
        log_event("PROCESS_RESTART", f"{self.name} count={self.restart_count}")
        self.start()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            log_event("PROCESS_STOP", self.name)


# ── Cloud Scheduler ────────────────────────────────────────────────────────────

class CloudScheduler(threading.Thread):
    """
    Cloud daily scheduler.
    - Runs Gmail triage + draft replies
    - Runs social post DRAFTS (writes to Pending_Approval/cloud/ — never posts)
    - Runs CEO briefing on Mondays (draft only)
    - Syncs vault via Git
    """

    def __init__(self, python_path: str):
        super().__init__(daemon=True)
        self.python    = python_path
        self._last_run = None
        self._stop     = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        logger.info(f"Cloud scheduler started — daily run at {BRIEFING_HOUR:02d}:00 UTC")
        while not self._stop.is_set():
            now   = datetime.now()
            today = now.date()
            if now.hour >= BRIEFING_HOUR and self._last_run != today:
                self._daily_cloud_run()
                self._last_run = today
            self._stop.wait(timeout=60)

    def _daily_cloud_run(self):
        logger.info("Cloud daily run starting...")
        log_event("CLOUD_DAILY_START", "")

        # 1. Sync vault from remote (git pull)
        self._sync_vault(direction="pull")

        # 2. Run process-inbox (draft only — no sends)
        self._run_briefing()

        # 3. Draft social posts (to Pending_Approval/cloud/ only)
        self._draft_social_posts()

        # 4. CEO Briefing on Mondays
        if datetime.now().strftime("%A") == "Monday":
            self._run_ceo_briefing()

        # 5. Write update file for Local to merge
        write_update(f"Cloud daily run completed at {datetime.now(timezone.utc).isoformat()}")

        # 6. Sync vault to remote (git push)
        self._sync_vault(direction="push")

        log_event("CLOUD_DAILY_DONE", "")

    def _sync_vault(self, direction: str):
        script = Path("scripts/sync_vault.py")
        if not script.exists():
            logger.warning("sync_vault.py not found — skipping sync")
            return
        try:
            r = subprocess.run(
                [self.python, str(script), f"--{direction}"],
                capture_output=True, text=True, timeout=60
            )
            if r.returncode == 0:
                logger.info(f"Vault sync ({direction}) complete")
                log_event(f"VAULT_SYNC_{direction.upper()}", "success")
            else:
                logger.warning(f"Vault sync ({direction}) failed: {r.stderr[:200]}")
                log_event(f"VAULT_SYNC_{direction.upper()}_ERROR", r.stderr[:200])
        except Exception as e:
            logger.error(f"Vault sync exception: {e}")

    def _run_briefing(self):
        try:
            r = subprocess.run(
                [self.python, "run_process_inbox.py"],
                capture_output=True, text=True, timeout=120
            )
            status = "success" if r.returncode == 0 else "error"
            log_event("CLOUD_BRIEFING", status)
            if r.returncode != 0:
                logger.warning(f"Briefing error: {r.stderr[:200]}")
        except Exception as e:
            logger.error(f"Briefing exception: {e}")

    def _draft_social_posts(self):
        """Draft social posts — output goes to Pending_Approval/cloud/ (not Approved/)."""
        for sched in ["linkedin_scheduler", "facebook_scheduler", "instagram_scheduler", "twitter_scheduler"]:
            script = Path(f"schedulers/{sched}.py")
            if not script.exists():
                continue
            try:
                env = os.environ.copy()
                env["CLOUD_DRAFT_ONLY"] = "true"  # schedulers respect this flag
                r = subprocess.run(
                    [self.python, str(script), "--dry-run"],
                    capture_output=True, text=True, timeout=60, env=env
                )
                if r.returncode == 0:
                    log_event(f"CLOUD_{sched.upper()}_DRAFT", "success")
            except Exception as e:
                logger.error(f"{sched} exception: {e}")

    def _run_ceo_briefing(self):
        try:
            r = subprocess.run(
                [self.python, "schedulers/ceo_briefing.py", "--force"],
                capture_output=True, text=True, timeout=120
            )
            status = "success" if r.returncode == 0 else "error"
            log_event("CLOUD_CEO_BRIEFING", status)
        except Exception as e:
            logger.error(f"CEO Briefing exception: {e}")


# ── Signal Handler (reads Local directives) ────────────────────────────────────

class SignalHandler(threading.Thread):
    """Reads /Signals/ directory for commands from Local agent."""

    def __init__(self):
        super().__init__(daemon=True)
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        logger.info("Signal handler started — watching /Signals/ for Local directives")
        while not self._stop.is_set():
            for sig in read_signals():
                content = sig["content"]
                fpath   = sig["file"]
                logger.info(f"Signal received: {fpath.name}")
                log_event("SIGNAL_RECEIVED", fpath.name)

                # Handle STOP signal
                if "STOP_CLOUD" in content:
                    logger.warning("STOP_CLOUD signal received — halting cloud agent")
                    (VAULT_PATH / "STOP.md").write_text("STOP from Local\n")

                # Archive processed signal
                archive = VAULT_PATH / "Done" / fpath.name
                fpath.rename(archive)

            self._stop.wait(timeout=30)


# ── Cloud Orchestrator Main ────────────────────────────────────────────────────

class CloudOrchestrator:
    def __init__(self):
        self.python    = get_python()
        self.stop_file = VAULT_PATH / "STOP.md"
        self.processes: list[ManagedProcess] = []
        self.scheduler: Optional[CloudScheduler] = None
        self.sig_handler: Optional[SignalHandler] = None
        self._running  = False

    def _build_processes(self) -> list[ManagedProcess]:
        """
        Cloud only runs watchers that are safe for cloud:
        - filesystem_watcher (watches drop_folder on cloud)
        - gmail_watcher      (monitors Gmail for new emails)
        - email_watcher      (sends drafts that Local approved)
        - ralph_watcher      (task chain daemon)

        Cloud does NOT run:
        - whatsapp_watcher   (stays on Local — QR session + phone)
        - linkedin_watcher   (posting — stays on Local after approval)
        - facebook_watcher   (posting — stays on Local after approval)
        - instagram_watcher  (posting — stays on Local after approval)
        - twitter_watcher    (posting — stays on Local after approval)
        """
        python = self.python
        processes = []

        processes.append(ManagedProcess(
            name="filesystem-watcher",
            cmd=[python, "watchers/filesystem_watcher.py"],
            enabled=True,
        ))

        gmail_creds = Path("credentials/gmail_credentials.json")
        processes.append(ManagedProcess(
            name="gmail-watcher",
            cmd=[python, "watchers/gmail_watcher.py"],
            enabled=gmail_creds.exists(),
        ))

        email_from = os.getenv("EMAIL_FROM", "")
        processes.append(ManagedProcess(
            name="email-watcher",
            cmd=[python, "watchers/email_watcher.py"],
            enabled=bool(email_from),
        ))

        processes.append(ManagedProcess(
            name="ralph-watcher",
            cmd=[python, "watchers/ralph_watcher.py"],
            enabled=True,
        ))

        return processes

    def start(self):
        logger.info("=" * 55)
        logger.info("AI Employee Cloud Orchestrator starting (Platinum Tier)")
        logger.info(f"Agent ID : {AGENT_ID}")
        logger.info(f"Vault    : {VAULT_PATH.resolve()}")
        logger.info(f"Python   : {self.python}")
        logger.info(f"Mode     : {'DRY RUN' if DRY_RUN else 'LIVE'}")
        logger.info("Zone     : Cloud (drafts only — no send/post)")
        logger.info("=" * 55)

        self.processes = self._build_processes()
        for proc in self.processes:
            proc.start()
            time.sleep(1)

        self.scheduler   = CloudScheduler(self.python)
        self.sig_handler = SignalHandler()
        self.scheduler.start()
        self.sig_handler.start()

        self._running = True
        enabled = len([p for p in self.processes if p.enabled])
        log_event("CLOUD_ORCHESTRATOR_START", f"processes={enabled} agent_id={AGENT_ID}")
        write_update(f"Cloud agent started. Processes: {enabled}. Mode: {'DRY RUN' if DRY_RUN else 'LIVE'}")

    def stop(self, signum=None, frame=None):
        logger.info("Stopping cloud orchestrator...")
        self._running = False
        if self.scheduler:
            self.scheduler.stop()
        if self.sig_handler:
            self.sig_handler.stop()
        for proc in self.processes:
            proc.stop()
        log_event("CLOUD_ORCHESTRATOR_STOP", "graceful")
        write_update("Cloud agent stopped gracefully.")
        sys.exit(0)

    def run(self):
        self.start()
        signal.signal(signal.SIGINT,  self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        logger.info("Cloud orchestrator running. Ctrl+C to stop.")

        while self._running:
            if self.stop_file.exists():
                logger.warning("STOP.md detected — halting cloud agent.")
                self.stop()

            for proc in self.processes:
                if proc.needs_restart():
                    proc.restart()
                    time.sleep(2)
                elif proc.enabled and proc.restart_count >= ManagedProcess.MAX_RESTARTS and not proc.is_running():
                    logger.error(f"{proc.name}: max restarts exceeded — giving up")

            time.sleep(10)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI Employee Cloud Orchestrator (Platinum Tier)")
    parser.add_argument("--dry-run", action="store_true", help="Log intended actions without executing")
    args = parser.parse_args()
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    orc = CloudOrchestrator()
    orc.run()


if __name__ == "__main__":
    main()
