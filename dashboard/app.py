"""
dashboard/app.py — AI Employee Web Dashboard

Run: python dashboard/app.py
Open: http://localhost:5000
"""

import os
import sys
import json
import re
import shutil
import subprocess
import base64
import hashlib
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, jsonify, request, redirect, url_for, session as flask_session
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

# ── Setup ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
VAULT_PATH = BASE_DIR / "AI_Employee_Vault"
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

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
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB
app.secret_key = "ai-employee-secret-2026-aqsa"

# ── Auth ─────────────────────────────────────────────────────────────────────
DASHBOARD_EMAIL    = "aqsashah000000@gmail.com"
DASHBOARD_PASSWORD = hashlib.sha256("aqsaahshah120".encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not flask_session.get("logged_in"):
            return jsonify({"error": "Unauthorized", "login_required": True}), 401
        return f(*args, **kwargs)
    return decorated


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


@app.route("/api/whatsapp/messages")
def api_whatsapp_messages():
    """Incoming WhatsApp messages from Inbox."""
    files = []
    for f in sorted(INBOX_DIR.glob("WHATSAPP_*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        content = f.read_text(encoding="utf-8", errors="ignore")
        contact = ""
        lines_text = []
        for line in content.splitlines():
            if line.startswith("contact:"):
                contact = line.replace("contact:", "").strip()
            if line.startswith("- ") and "(no text)" not in line:
                lines_text.append(line[2:].strip())
        files.append({
            "name": f.name,
            "contact": contact,
            "messages": lines_text,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return jsonify(files)


@app.route("/api/whatsapp/drafts")
def api_whatsapp_drafts():
    """Pending WhatsApp reply drafts."""
    files = []
    for f in sorted(PENDING_DIR.glob("WHATSAPP_REPLY_*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        content = f.read_text(encoding="utf-8", errors="ignore")
        contact = ""
        reply = ""
        original = []
        import re as _re
        m = _re.search(r"^contact:\s*(.+)$", content, _re.MULTILINE)
        if m:
            contact = m.group(1).strip()
        m2 = _re.search(r"## Reply Content\s*\n(.*?)(?:\n---|\Z)", content, _re.DOTALL)
        if m2:
            reply = m2.group(1).strip()
        for line in content.splitlines():
            if line.startswith("- ") and "(no text)" not in line:
                original.append(line[2:].strip())
        files.append({
            "name": f.name,
            "contact": contact,
            "original": original,
            "reply": reply,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return jsonify(files)


@app.route("/api/whatsapp/approve/<filename>", methods=["POST"])
@login_required
def api_whatsapp_approve(filename):
    """Move WhatsApp reply draft to Approved."""
    src = PENDING_DIR / filename
    if not src.exists():
        return jsonify({"error": "File not found"}), 404
    # Allow editing reply content before approving
    data = request.get_json() or {}
    if "reply" in data:
        content = src.read_text(encoding="utf-8")
        import re as _re
        content = _re.sub(
            r"(## Reply Content\s*\n)(.*?)(\n---|\Z)",
            lambda m: m.group(1) + data["reply"] + m.group(3),
            content, flags=_re.DOTALL
        )
        src.write_text(content, encoding="utf-8")
    shutil.move(str(src), str(APPROVED_DIR / filename))
    return jsonify({"status": "approved", "file": filename})


@app.route("/api/whatsapp/reject/<filename>", methods=["POST"])
@login_required
def api_whatsapp_reject(filename):
    """Reject a WhatsApp draft."""
    src = PENDING_DIR / filename
    if src.exists():
        shutil.move(str(src), str(REJECTED_DIR / filename))
    return jsonify({"status": "rejected"})


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


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    pwd   = hashlib.sha256(data.get("password", "").encode()).hexdigest()
    if email == DASHBOARD_EMAIL and pwd == DASHBOARD_PASSWORD:
        flask_session["logged_in"] = True
        return jsonify({"status": "ok"})
    return jsonify({"error": "Invalid email or password"}), 401


@app.route("/api/logout", methods=["POST"])
def api_logout():
    flask_session.clear()
    return jsonify({"status": "logged_out"})


@app.route("/api/auth-status")
def api_auth_status():
    return jsonify({"logged_in": bool(flask_session.get("logged_in"))})


def _trigger_watcher(filename: str):
    """Run the appropriate watcher --post-now in background after approval."""
    import threading
    name_upper = filename.upper()
    if "TWITTER" in name_upper:
        watcher = "watchers/twitter_watcher.py"
    elif "INSTAGRAM" in name_upper:
        watcher = "watchers/instagram_watcher.py"
    elif "FACEBOOK" in name_upper:
        watcher = "watchers/facebook_watcher.py"
    elif "LINKEDIN" in name_upper:
        watcher = "watchers/linkedin_watcher.py"
    elif "WHATSAPP" in name_upper:
        watcher = "watchers/whatsapp_watcher.py"
    else:
        return

    script = BASE_DIR / watcher
    if not script.exists():
        return

    def run():
        try:
            proc = subprocess.Popen(
                [sys.executable, str(script), "--post-now"],
                cwd=str(BASE_DIR),
                env={**os.environ},
            )
            proc.wait()
        except Exception as e:
            print(f"[Dashboard] Watcher trigger failed: {e}")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    print(f"[Dashboard] Triggered watcher for: {filename}")


@app.route("/api/approve/<filename>", methods=["POST"])
@login_required
def api_approve(filename):
    src  = PENDING_DIR / filename
    dest = APPROVED_DIR / filename
    if src.exists():
        shutil.move(str(src), str(dest))
        _trigger_watcher(filename)
        return jsonify({"status": "approved", "file": filename})
    return jsonify({"error": "File not found"}), 404


@app.route("/api/reject/<filename>", methods=["POST"])
@login_required
def api_reject(filename):
    src  = PENDING_DIR / filename
    dest = REJECTED_DIR / filename
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.move(str(src), str(dest))
        return jsonify({"status": "rejected", "file": filename})
    return jsonify({"error": "File not found"}), 404


@app.route("/api/inbox/<filename>", methods=["DELETE"])
def api_inbox_delete(filename):
    """Permanently delete an inbox file."""
    target = INBOX_DIR / filename
    if ".." in filename or "/" in filename or "\\" in filename:
        return jsonify({"error": "Invalid filename"}), 400
    if target.exists():
        target.unlink()
        return jsonify({"status": "deleted", "file": filename})
    return jsonify({"error": "File not found"}), 404


@app.route("/api/draft/<platform>", methods=["POST"])
@login_required
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
            capture_output=True, text=True, cwd=str(BASE_DIR), timeout=180
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


@app.route("/api/upload-session/<platform>", methods=["POST"])
def api_upload_session(platform):
    """Receive session JSON from laptop and save it on this machine."""
    allowed = {"linkedin", "instagram", "facebook", "twitter", "whatsapp"}
    if platform not in allowed:
        return jsonify({"error": "Invalid platform"}), 400
    data = request.get_json()
    if not data or "session" not in data:
        return jsonify({"error": "No session data"}), 400
    session_dir = BASE_DIR / "credentials" / f"{platform}_session"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / "state.json"
    session_file.write_text(json.dumps(data["session"]), encoding="utf-8")
    return jsonify({"status": "saved", "platform": platform})


@app.route("/api/sync-sessions", methods=["POST"])
def api_sync_sessions():
    """Sync all sessions from request body to this machine."""
    sessions = request.get_json() or {}
    saved = []
    for platform, session_data in sessions.items():
        session_dir = BASE_DIR / "credentials" / f"{platform}_session"
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "state.json").write_text(json.dumps(session_data), encoding="utf-8")
        saved.append(platform)
    return jsonify({"status": "synced", "platforms": saved})


# ── Chat ─────────────────────────────────────────────────────────────────────

@app.route("/chat")
def chat_page():
    if not flask_session.get("logged_in"):
        return redirect(url_for("index"))
    return render_template("chat.html")


def _build_system_prompt() -> str:
    """Build a dynamic system prompt using current vault state."""
    stats = get_vault_stats()
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d")
    weekday  = today.strftime("%A")

    pending_files = [f["name"] for f in get_files(PENDING_DIR)]
    pending_list  = "\n".join(f"  - {n}" for n in pending_files) if pending_files else "  (none)"

    recent_logs = get_recent_logs(30)
    logs_text   = "\n".join(recent_logs) if recent_logs else "(no recent activity)"

    return f"""You are Aqsa Shah's AI Employee assistant. You manage her social media and communications.

Today: {date_str} ({weekday})

Current vault status:
- Pending approval: {stats['pending']} items
- Done: {stats['done']} items
- Inbox: {stats['inbox']} messages

Pending items:
{pending_list}

Recent activity (last 24h):
{logs_text}

You can:
1. Create social media post drafts (goes to Pending Approval for Aqsa to approve)
2. Generate captions for uploaded images/videos
3. Approve or reject pending drafts
4. Answer questions about past activity from logs
5. Post to LinkedIn, Facebook, Instagram, Twitter

Platform character limits: LinkedIn=1300, Twitter=280, Facebook=500, Instagram=2200

When creating posts with media, mention the media file path in the draft.
Always respond in the same language Aqsa uses (Roman Urdu or English).
Be concise and friendly, like a smart employee.
"""


def _execute_tool(tool_name: str, tool_input: dict) -> tuple:
    """
    Execute a Claude tool call server-side.
    Returns (result_str, action_dict).
    """
    action = {"tool": tool_name, "input": tool_input}
    today_str = datetime.now().strftime("%Y-%m-%d")

    if tool_name == "list_pending":
        files = [f["name"] for f in get_files(PENDING_DIR)]
        result = json.dumps(files)
        action["result"] = files
        return result, action

    elif tool_name == "get_activity":
        date = tool_input.get("date", "today")
        if date == "today":
            date = datetime.now().strftime("%Y-%m-%d")
        log_file = LOGS_DIR / f"{date}.log"
        if log_file.exists():
            lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            result = "\n".join(lines[-50:])
        else:
            result = f"No log found for {date}"
        action["result"] = result
        return result, action

    elif tool_name == "approve_draft":
        filename = tool_input.get("filename", "")
        src  = PENDING_DIR / filename
        dest = APPROVED_DIR / filename
        if src.exists():
            shutil.move(str(src), str(dest))
            result = f"Approved: {filename}"
            action["status"] = "approved"
        else:
            result = f"File not found: {filename}"
            action["status"] = "not_found"
        action["result"] = result
        return result, action

    elif tool_name == "reject_draft":
        filename = tool_input.get("filename", "")
        src  = PENDING_DIR / filename
        dest = REJECTED_DIR / filename
        if src.exists():
            shutil.move(str(src), str(dest))
            result = f"Rejected: {filename}"
            action["status"] = "rejected"
        else:
            result = f"File not found: {filename}"
            action["status"] = "not_found"
        action["result"] = result
        return result, action

    elif tool_name == "create_draft":
        platform   = tool_input.get("platform", "linkedin").lower()
        content    = tool_input.get("content", "")
        media_path = tool_input.get("media_path", None)
        caption    = tool_input.get("caption", None)

        platforms_to_create = []
        if platform == "all":
            platforms_to_create = ["linkedin", "facebook", "instagram", "twitter"]
        else:
            platforms_to_create = [platform]

        created = []
        for plat in platforms_to_create:
            filename = f"{plat.upper()}_{today_str}.md"
            dest = PENDING_DIR / filename
            # Avoid overwriting — append counter if exists
            counter = 1
            while dest.exists():
                filename = f"{plat.upper()}_{today_str}_{counter}.md"
                dest = PENDING_DIR / filename
                counter += 1

            media_line = f"media: {media_path}" if media_path else "media: null"
            caption_line = f"caption: {caption}" if caption else ""
            frontmatter_extra = f"\n{caption_line}" if caption_line else ""

            file_text = f"""---
platform: {plat}
date: {today_str}
status: pending
{media_line}{frontmatter_extra}
---

{content}
"""
            dest.write_text(file_text, encoding="utf-8")
            created.append(filename)

        result = json.dumps({"created": created})
        action["created"] = created
        action["result"] = result
        return result, action

    else:
        result = f"Unknown tool: {tool_name}"
        action["result"] = result
        return result, action


CHAT_TOOLS = [
    {
        "name": "create_draft",
        "description": "Create a social media post draft file in Pending_Approval. Use platform='all' to create for all platforms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Platform: linkedin, facebook, instagram, twitter, or all",
                    "enum": ["linkedin", "facebook", "instagram", "twitter", "all"]
                },
                "content": {
                    "type": "string",
                    "description": "The post text/content"
                },
                "media_path": {
                    "type": "string",
                    "description": "Optional path to media file (image or video)"
                },
                "caption": {
                    "type": "string",
                    "description": "Optional caption for the media"
                }
            },
            "required": ["platform", "content"]
        }
    },
    {
        "name": "list_pending",
        "description": "List all files currently in Pending_Approval folder",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_activity",
        "description": "Get activity log for a specific date",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format or 'today'"
                }
            }
        }
    },
    {
        "name": "approve_draft",
        "description": "Approve a pending draft by moving it to Approved folder",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename of the draft to approve (e.g. LINKEDIN_2026-03-30.md)"
                }
            },
            "required": ["filename"]
        }
    },
    {
        "name": "reject_draft",
        "description": "Reject a pending draft by moving it to Rejected folder",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename of the draft to reject"
                }
            },
            "required": ["filename"]
        }
    }
]


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    """AI chat endpoint with tool use and optional image/video upload."""
    import anthropic

    # ── Parse form data ───────────────────────────────────────────────────────
    message   = request.form.get("message", "").strip()
    history_raw = request.form.get("history", "[]")
    platforms_raw = request.form.get("platforms", "")
    uploaded_file = request.files.get("file")

    try:
        history = json.loads(history_raw)
    except Exception:
        history = []

    # ── Handle file upload ────────────────────────────────────────────────────
    media_path = None
    media_b64  = None
    media_mime = None
    is_video   = False

    if uploaded_file and uploaded_file.filename:
        ext = Path(uploaded_file.filename).suffix.lower().lstrip(".")
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"{ts}_{re.sub(r'[^a-zA-Z0-9._-]', '_', uploaded_file.filename)}"
        save_path = UPLOADS_DIR / safe_name
        uploaded_file.save(str(save_path))
        media_path = str(save_path)

        image_exts = {"jpg", "jpeg", "png", "gif", "webp"}
        video_exts = {"mp4", "mov", "avi", "mkv", "webm"}

        if ext in image_exts:
            mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                        "gif": "image/gif", "webp": "image/webp"}
            media_mime = mime_map.get(ext, "image/jpeg")
            with open(save_path, "rb") as fh:
                media_b64 = base64.standard_b64encode(fh.read()).decode("utf-8")
        elif ext in video_exts:
            is_video = True

    # ── Build message list for Claude ────────────────────────────────────────
    # History is list of {role, content} pairs
    messages = []
    for h in history:
        role    = h.get("role", "user")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    # Build current user message content
    current_content = []
    if media_b64 and media_mime:
        current_content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_mime,
                "data": media_b64
            }
        })

    text_parts = []
    if message:
        text_parts.append(message)
    if is_video:
        text_parts.append(f"[Video uploaded: {Path(media_path).name}]")
    if platforms_raw:
        text_parts.append(f"[Target platforms: {platforms_raw}]")

    user_text = "\n".join(text_parts) if text_parts else "(no text)"
    current_content.append({"type": "text", "text": user_text})

    messages.append({"role": "user", "content": current_content})

    # ── Call Claude with agentic tool loop ───────────────────────────────────
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    system_prompt = _build_system_prompt()

    actions_log    = []
    drafts_created = []
    final_reply    = ""
    max_iters      = 8

    for _ in range(max_iters):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system_prompt,
            tools=CHAT_TOOLS,
            messages=messages
        )

        # Collect any text from this response turn
        for block in response.content:
            if hasattr(block, "text"):
                final_reply = block.text  # Keep last text block

        # If no tool calls, we're done
        if response.stop_reason != "tool_use":
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result_str, action = _execute_tool(block.name, block.input)
                actions_log.append(action)
                if block.name == "create_draft" and "created" in action:
                    drafts_created.extend(action["created"])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str
                })

        # Append assistant turn + tool results to messages
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return jsonify({
        "reply": final_reply,
        "actions": actions_log,
        "drafts_created": drafts_created,
        "media_path": media_path
    })


if __name__ == "__main__":
    print("=" * 50)
    print("  AI Employee Dashboard")
    print("  Open: http://localhost:5000")
    print("=" * 50)
    app.run(debug=False, host="0.0.0.0", port=5000)
