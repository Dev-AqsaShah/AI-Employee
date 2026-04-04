"""
scripts/health_monitor.py — Process health check + alerting (Platinum Tier)

Monitors cloud services and writes health status to vault.
Local agent reads /Updates/HEALTH_*.md to track cloud health.

Usage:
    python scripts/health_monitor.py              # Run once
    python scripts/health_monitor.py --watch      # Run every 5 minutes
    python scripts/health_monitor.py --status     # Print current status
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

VAULT_PATH = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
AGENT_ID   = os.getenv("AGENT_ID", "cloud")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [HealthMonitor] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("HealthMonitor")

SERVICES_TO_CHECK = [
    "ai-employee-cloud",
    "ai-employee-vault-sync",
]


def check_systemd_service(name: str) -> dict:
    """Check if a systemd service is running (Linux only)."""
    try:
        r = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True
        )
        return {"name": name, "status": r.stdout.strip(), "ok": r.returncode == 0}
    except FileNotFoundError:
        return {"name": name, "status": "systemctl-not-available", "ok": None}


def check_python_process(script_name: str) -> dict:
    """Check if a Python process is running by script name."""
    try:
        r = subprocess.run(
            ["pgrep", "-f", script_name],
            capture_output=True, text=True
        )
        pids = r.stdout.strip().split() if r.stdout.strip() else []
        return {"name": script_name, "pids": pids, "ok": len(pids) > 0}
    except FileNotFoundError:
        # Windows: use tasklist
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq python.exe"],
                capture_output=True, text=True
            )
            ok = script_name in r.stdout
            return {"name": script_name, "ok": ok}
        except Exception:
            return {"name": script_name, "ok": None, "error": "process-check-unavailable"}


def check_vault_health() -> dict:
    """Check vault folder sizes and recent activity."""
    results = {}
    folders = ["Needs_Action", "Inbox", "Pending_Approval", "In_Progress", "Done"]
    for folder in folders:
        path = VAULT_PATH / folder
        if path.exists():
            files = [f for f in path.rglob("*.md") if f.name != ".gitkeep"]
            results[folder] = len(files)
        else:
            results[folder] = "MISSING"

    # Check last log entry
    logs_dir = VAULT_PATH / "Logs"
    last_log = "none"
    if logs_dir.exists():
        log_files = sorted(logs_dir.glob("*.log"), reverse=True)
        if log_files:
            lines = log_files[0].read_text(encoding="utf-8", errors="ignore").splitlines()
            last_log = lines[-1][:100] if lines else "empty"

    results["last_log"] = last_log
    return results


def check_odoo() -> dict:
    """Check if Odoo is reachable."""
    import urllib.request
    odoo_url = os.getenv("ODOO_URL", "http://localhost:8069")
    try:
        r = urllib.request.urlopen(f"{odoo_url}/web/health", timeout=5)
        return {"url": odoo_url, "status": r.status, "ok": True}
    except Exception as e:
        return {"url": odoo_url, "ok": False, "error": str(e)[:100]}


def run_health_check() -> dict:
    """Run all health checks and return summary."""
    ts = datetime.now(timezone.utc).isoformat()
    logger.info(f"Running health check at {ts}")

    report = {
        "timestamp": ts,
        "agent_id":  AGENT_ID,
        "systemd":   [],
        "vault":     {},
        "odoo":      {},
        "overall":   "healthy",
    }

    # Systemd services
    for svc in SERVICES_TO_CHECK:
        result = check_systemd_service(svc)
        report["systemd"].append(result)
        if result.get("ok") is False:
            report["overall"] = "degraded"

    # Vault health
    report["vault"] = check_vault_health()

    # Odoo
    report["odoo"] = check_odoo()
    if not report["odoo"].get("ok"):
        report["overall"] = "degraded"

    return report


def write_health_update(report: dict):
    """Write health report to /Updates/ for Local agent."""
    updates_dir = VAULT_PATH / "Updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    status_icon = "OK" if report["overall"] == "healthy" else "WARN"
    vault = report["vault"]

    content = f"""---
type: health_report
agent: {report['agent_id']}
timestamp: {report['timestamp']}
status: {report['overall']}
---

# Health Report [{status_icon}] — {report['timestamp']}

## Services
"""
    for svc in report["systemd"]:
        ok_str = "running" if svc.get("ok") else f"DOWN ({svc.get('status', '?')})"
        content += f"- {svc['name']}: {ok_str}\n"

    content += f"""
## Vault Queue
- Needs_Action: {vault.get('Needs_Action', '?')} items
- Inbox: {vault.get('Inbox', '?')} items
- Pending_Approval: {vault.get('Pending_Approval', '?')} items
- In_Progress: {vault.get('In_Progress', '?')} items
- Done: {vault.get('Done', '?')} total

## Odoo
- Status: {"OK" if report['odoo'].get('ok') else f"DOWN — {report['odoo'].get('error', '?')}"}

## Last Log Entry
```
{vault.get('last_log', 'none')}
```
"""
    path = updates_dir / f"HEALTH_{ts}.md"
    path.write_text(content, encoding="utf-8")
    logger.info(f"Health report written: {path.name}")


def watch_mode(interval: int = 300):
    """Run health checks continuously."""
    logger.info(f"Health monitor watch mode — checking every {interval}s")
    while True:
        if (VAULT_PATH / "STOP.md").exists():
            logger.warning("STOP.md detected — halting health monitor")
            break
        try:
            report = run_health_check()
            write_health_update(report)
            status = report["overall"].upper()
            logger.info(f"Health status: {status}")
        except Exception as e:
            logger.error(f"Health check error: {e}")
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="AI Employee Health Monitor")
    parser.add_argument("--watch",    action="store_true", help="Run continuously")
    parser.add_argument("--status",   action="store_true", help="Print status and exit")
    parser.add_argument("--interval", type=int, default=300, help="Watch interval seconds")
    args = parser.parse_args()

    if args.watch:
        watch_mode(args.interval)
    else:
        report = run_health_check()
        write_health_update(report)
        print(f"\nHealth: {report['overall'].upper()}")
        print(f"Vault queue: {report['vault']}")
        print(f"Odoo: {'OK' if report['odoo'].get('ok') else 'DOWN'}")
        sys.exit(0 if report["overall"] == "healthy" else 1)


if __name__ == "__main__":
    main()
