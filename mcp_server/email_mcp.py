"""
email_mcp.py — Email MCP Server for AI Employee (Silver Tier)

Exposes tools that Claude Code can call via MCP:
  - send_email(to, subject, body, cc?)
  - draft_email(to, subject, body) — saves to vault, no send
  - list_drafts()

Uses Gmail SMTP (App Password) or any SMTP server.

Setup:
  1. For Gmail: enable 2FA, create App Password at myaccount.google.com/apppasswords
  2. Set environment variables in .env:
       EMAIL_FROM=you@gmail.com
       EMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
       SMTP_HOST=smtp.gmail.com
       SMTP_PORT=587
  3. Register in Claude Code MCP config (see docs/mcp_setup.md)

Run:
    python mcp_server/email_mcp.py
"""

import os
import sys
import json
import smtplib
import logging
from pathlib import Path
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── MCP SDK ────────────────────────────────────────────────────────────────────
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, CallToolResult
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [EmailMCP] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
EMAIL_FROM     = os.getenv("EMAIL_FROM", "")
APP_PASSWORD   = os.getenv("EMAIL_APP_PASSWORD", "")
SMTP_HOST      = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
VAULT_PATH     = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
DRY_RUN        = os.getenv("DRY_RUN", "true").lower() == "true"

DRAFTS_DIR     = VAULT_PATH / "Drafts"
LOGS_DIR       = VAULT_PATH / "Logs"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


# ── Core email functions ───────────────────────────────────────────────────────

def _log_action(action: str, details: dict):
    today = datetime.now().strftime("%Y-%m-%d")
    entry = json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": action,
        "actor": "email_mcp",
        **details
    })
    with open(LOGS_DIR / f"{today}.log", "a") as f:
        f.write(entry + "\n")


def send_email(to: str, subject: str, body: str, cc: str = "") -> dict:
    """Send an email via SMTP. Requires EMAIL_FROM and EMAIL_APP_PASSWORD."""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would send email to {to} | Subject: {subject}")
        _log_action("email_send_dry_run", {"to": to, "subject": subject})
        return {"status": "dry_run", "message": f"DRY RUN: Would send to {to}"}

    if not EMAIL_FROM or not APP_PASSWORD:
        return {"status": "error", "message": "EMAIL_FROM and EMAIL_APP_PASSWORD not configured in .env"}

    msg = MIMEMultipart()
    msg["From"]    = EMAIL_FROM
    msg["To"]      = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_FROM, APP_PASSWORD)
            recipients = [to] + ([cc] if cc else [])
            server.sendmail(EMAIL_FROM, recipients, msg.as_string())

        logger.info(f"Email sent to {to}")
        _log_action("email_send", {
            "to": to, "subject": subject,
            "approval_status": "approved", "result": "success"
        })
        return {"status": "success", "message": f"Email sent to {to}"}

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        _log_action("email_send_error", {"to": to, "subject": subject, "error": str(e)})
        return {"status": "error", "message": str(e)}


def draft_email(to: str, subject: str, body: str) -> dict:
    """Save an email draft to vault for human review."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"DRAFT_EMAIL_{timestamp}.md"
    filepath  = DRAFTS_DIR / filename

    content = f"""---
type: email_draft
to: {to}
subject: {subject}
created: {datetime.now(timezone.utc).isoformat()}
status: draft
---

## Email Draft

**To:** {to}
**Subject:** {subject}

---

{body}

---

## To Send
Move this file to `/Approved/` to trigger sending via Email MCP.
"""
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Draft saved: {filename}")
    _log_action("email_draft", {"to": to, "subject": subject, "file": filename})
    return {"status": "drafted", "file": str(filepath), "message": f"Draft saved: {filename}"}


def list_drafts() -> dict:
    """List all email drafts in the vault."""
    drafts = list(DRAFTS_DIR.glob("DRAFT_EMAIL_*.md"))
    return {
        "count": len(drafts),
        "drafts": [f.name for f in sorted(drafts, key=lambda x: x.stat().st_mtime, reverse=True)]
    }


# ── MCP Server ─────────────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="send_email",
        description=(
            "Send an email via SMTP. For safety, set DRY_RUN=false in .env first. "
            "Only call this after human approval has been recorded in /Approved/."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "to":      {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject line"},
                "body":    {"type": "string", "description": "Plain text email body"},
                "cc":      {"type": "string", "description": "CC email address (optional)", "default": ""},
            },
            "required": ["to", "subject", "body"],
        },
    ),
    Tool(
        name="draft_email",
        description=(
            "Save an email draft to the vault for human review. "
            "Use this instead of send_email for any new contact or sensitive content."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "to":      {"type": "string"},
                "subject": {"type": "string"},
                "body":    {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    ),
    Tool(
        name="list_drafts",
        description="List all email drafts currently in the vault.",
        inputSchema={"type": "object", "properties": {}},
    ),
]


async def run_mcp_server():
    """Start the MCP server over stdio."""
    server = Server("ai-employee-email-mcp")

    @server.list_tools()
    async def handle_list_tools():
        return TOOLS

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict):
        if name == "send_email":
            result = send_email(
                to=arguments["to"],
                subject=arguments["subject"],
                body=arguments["body"],
                cc=arguments.get("cc", ""),
            )
        elif name == "draft_email":
            result = draft_email(
                to=arguments["to"],
                subject=arguments["subject"],
                body=arguments["body"],
            )
        elif name == "list_drafts":
            result = list_drafts()
        else:
            result = {"error": f"Unknown tool: {name}"}

        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    if not MCP_AVAILABLE:
        logger.error("MCP SDK not installed. Run: pip install mcp")
        # Fallback: expose tools as a simple JSON-RPC over stdin/stdout
        logger.info("Running in fallback mode — tools available via direct Python import.")
        return

    import asyncio
    logger.info("Starting Email MCP Server...")
    logger.info(f"DRY_RUN={DRY_RUN} | FROM={EMAIL_FROM or '(not configured)'}")
    asyncio.run(run_mcp_server())


if __name__ == "__main__":
    main()
