"""
dashboard/app.py — AI Employee Web Dashboard

Run: python dashboard/app.py
Open: http://localhost:5000
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, jsonify, request, redirect, url_for

# ── Setup ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
VAULT_PATH = BASE_DIR / "AI_Employee_Vault"

PENDING_DIR  = VAULT_PATH / "Pending_Approval"
APPROVED_DIR = VAULT_PATH / "Approved"
REJECTED_DIR = VAULT_PATH / "Rejected"
DONE_DIR     = VAULT_PATH / "Done"
INBOX_DIR    = VAULT_PATH / "Inbox"
NEEDS_DIR    = VAULT_PATH / "Needs_Action"
LOGS_DIR     = VAULT_PATH / "Logs"

for d in [PENDING_DIR, APPROVED_DIR, REJECTED_DIR, DONE_DIR, INBOX_DIR, NEEDS_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))
app.config["TEMPLATES_AUTO_RELOAD"] = True


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_files(folder: Path) -> list:
    """Get markdown files from a folder with metadata."""
    files = []
    for f in sorted(folder.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat  = f.stat()
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        # Extract a preview (first non-empty, non-frontmatter line)
        preview = ""
        in_frontmatter = False
        for line in lines:
            if line.strip() == "---":
                in_frontmatter = not in_frontmatter
                continue
            if in_frontmatter:
                continue
            if line.strip() and not line.startswith("#"):
                preview = line.strip()[:120]
                break
        files.append({
            "name": f.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "preview": preview,
            "platform": _detect_platform(f.name),
        })
    return files


def _detect_platform(filename: str) -> str:
    name = filename.upper()
    if "LINKEDIN"  in name: return "linkedin"
    if "INSTAGRAM" in name: return "instagram"
    if "TWITTER"   in name: return "twitter"
    if "FACEBOOK"  in name: return "facebook"
    if "WHATSAPP"  in name: return "whatsapp"
    if "EMAIL"     in name: return "email"
    return "general"


def get_vault_stats() -> dict:
    return {
        "pending":  len(list(PENDING_DIR.glob("*.md"))),
        "approved": len(list(APPROVED_DIR.glob("*.md"))),
        "rejected": len(list(REJECTED_DIR.glob("*.md"))),
        "done":     len(list(DONE_DIR.glob("*.md"))),
        "inbox":    len(list(INBOX_DIR.glob("*.md"))),
        "needs_action": len(list(NEEDS_DIR.glob("*.md"))),
    }


def get_recent_logs(n: int = 50) -> list:
    """Get last n log lines from today's log."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"{today}.log"
    if not log_file.exists():
        # Try yesterday
        from datetime import timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        log_file = LOGS_DIR / f"{yesterday}.log"
    if not log_file.exists():
        return []
    lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[-n:][::-1]  # Latest first


def get_file_content(folder: Path, filename: str) -> str:
    f = folder / filename
    if f.exists():
        return f.read_text(encoding="utf-8", errors="ignore")
    return ""


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    stats   = get_vault_stats()
    pending = get_files(PENDING_DIR)
    return render_template("index.html", stats=stats, pending=pending)


@app.route("/api/stats")
def api_stats():
    return jsonify(get_vault_stats())


@app.route("/api/pending")
def api_pending():
    return jsonify(get_files(PENDING_DIR))


@app.route("/api/approved")
def api_approved():
    return jsonify(get_files(APPROVED_DIR))


@app.route("/api/done")
def api_done():
    return jsonify(get_files(DONE_DIR))


@app.route("/api/rejected")
def api_rejected():
    return jsonify(get_files(REJECTED_DIR))


@app.route("/api/inbox")
def api_inbox():
    return jsonify(get_files(INBOX_DIR))


@app.route("/api/needs")
def api_needs():
    return jsonify(get_files(NEEDS_DIR))


@app.route("/api/briefings")
def api_briefings():
    briefings_dir = VAULT_PATH / "Briefings"
    briefings_dir.mkdir(parents=True, exist_ok=True)
    return jsonify(get_files(briefings_dir))


@app.route("/api/logs")
def api_logs():
    return jsonify(get_recent_logs(100))


@app.route("/api/file/<folder>/<filename>")
def api_file(folder, filename):
    folder_map = {
        "pending":   PENDING_DIR,
        "approved":  APPROVED_DIR,
        "done":      DONE_DIR,
        "inbox":     INBOX_DIR,
        "rejected":  REJECTED_DIR,
        "needs":     NEEDS_DIR,
        "briefings": VAULT_PATH / "Briefings",
    }
    d = folder_map.get(folder)
    if not d:
        return jsonify({"error": "Invalid folder"}), 400
    content = get_file_content(d, filename)
    return jsonify({"content": content})


@app.route("/api/approve/<filename>", methods=["POST"])
def api_approve(filename):
    src  = PENDING_DIR / filename
    dest = APPROVED_DIR / filename
    if src.exists():
        shutil.move(str(src), str(dest))
        return jsonify({"status": "approved", "file": filename})
    return jsonify({"error": "File not found"}), 404


@app.route("/api/reject/<filename>", methods=["POST"])
def api_reject(filename):
    src  = PENDING_DIR / filename
    dest = REJECTED_DIR / filename
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.move(str(src), str(dest))
        return jsonify({"status": "rejected", "file": filename})
    return jsonify({"error": "File not found"}), 404


@app.route("/api/draft/<platform>", methods=["POST"])
def api_draft(platform):
    """Trigger a post scheduler to draft a post now."""
    scheduler_map = {
        "linkedin":  "schedulers/linkedin_scheduler.py",
        "instagram": "schedulers/instagram_scheduler.py",
        "twitter":   "schedulers/twitter_scheduler.py",
        "facebook":  "schedulers/facebook_scheduler.py",
    }
    script = scheduler_map.get(platform)
    if not script:
        return jsonify({"error": "Invalid platform"}), 400

    try:
        result = subprocess.run(
            [sys.executable, script, "--force"],
            capture_output=True, text=True, cwd=str(BASE_DIR), timeout=60
        )
        if result.returncode == 0:
            return jsonify({"status": "drafted", "platform": platform})
        else:
            return jsonify({"status": "error", "detail": result.stderr[-300:]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/watcher-status")
def api_watcher_status():
    """Check which watchers are running via process list."""
    import psutil
    watchers = ["filesystem_watcher", "gmail_watcher", "linkedin_watcher",
                "facebook_watcher", "instagram_watcher", "twitter_watcher",
                "whatsapp_watcher", "ralph_watcher", "email_watcher"]
    status = {}
    running_scripts = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            running_scripts.append(cmdline)
        except Exception:
            pass

    for w in watchers:
        status[w] = any(w in s for s in running_scripts)

    return jsonify(status)


if __name__ == "__main__":
    print("=" * 50)
    print("  AI Employee Dashboard")
    print("  Open: http://localhost:5000")
    print("=" * 50)
    app.run(debug=False, host="0.0.0.0", port=5000)
