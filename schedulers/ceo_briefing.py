"""
ceo_briefing.py — Weekly CEO Business Briefing

Runs every Monday (or on --force). Collects data from all sources,
then uses Claude API to generate a comprehensive weekly business audit.

Report includes:
  - Activity summary (tasks done, emails, posts)
  - Revenue vs targets (from Business_Goals.md + Odoo if available)
  - Pending items & bottlenecks
  - AI-generated insights, wins, and recommendations

Output saved to: AI_Employee_Vault/Briefings/CEO_BRIEFING_YYYY-MM-DD.md

Usage:
    python schedulers/ceo_briefing.py             # Run (Mondays only)
    python schedulers/ceo_briefing.py --force     # Force run any day
    python schedulers/ceo_briefing.py --dry-run   # Preview without saving
    python schedulers/ceo_briefing.py --email     # Also email the briefing
"""

import os
import re
import sys
import json
import logging
import argparse
import smtplib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CEOBriefing] %(levelname)s: %(message)s",
)
logger = logging.getLogger("CEOBriefing")

# ── Config ──────────────────────────────────────────────────────────────────────

VAULT_PATH        = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
EMAIL_FROM        = os.getenv("EMAIL_FROM", "")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")
SMTP_HOST         = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT         = int(os.getenv("SMTP_PORT", "587"))

BRIEFINGS_DIR  = VAULT_PATH / "Briefings"
LOGS_DIR       = VAULT_PATH / "Logs"
DONE_DIR       = VAULT_PATH / "Done"
PENDING_DIR    = VAULT_PATH / "Pending_Approval"
NEEDS_ACTION   = VAULT_PATH / "Needs_Action"
GOALS_FILE     = VAULT_PATH / "Business_Goals.md"
DASHBOARD_FILE = VAULT_PATH / "Dashboard.md"
HANDBOOK_FILE  = VAULT_PATH / "Company_Handbook.md"


# ── Data Collectors ─────────────────────────────────────────────────────────────

def get_week_range() -> tuple[datetime, datetime]:
    """Return start (Monday) and end (Sunday) of current week."""
    today = datetime.now()
    start = today - timedelta(days=today.weekday())  # Monday
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end   = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return start, end


def collect_logs_data(week_start: datetime, week_end: datetime) -> dict:
    """Parse log files for the past week."""
    data = {
        "total_events": 0,
        "linkedin_posts": 0,
        "facebook_posts": 0,
        "emails_sent": 0,
        "emails_processed": 0,
        "tasks_done": 0,
        "errors": [],
        "raw_lines": [],
    }

    if not LOGS_DIR.exists():
        return data

    # Check logs for each day in the week
    current = week_start
    while current <= week_end:
        log_file = LOGS_DIR / f"{current.strftime('%Y-%m-%d')}.log"
        if log_file.exists():
            for line in log_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                data["total_events"] += 1
                data["raw_lines"].append(line)

                # Count specific events
                if "LINKEDIN_POST_SUCCESS" in line or "linkedin post success" in line.lower():
                    data["linkedin_posts"] += 1
                elif "FACEBOOK_POST_SUCCESS" in line or "facebook post success" in line.lower():
                    data["facebook_posts"] += 1
                elif "EMAIL_SENT" in line or "email success" in line.lower():
                    data["emails_sent"] += 1
                elif "process-inbox" in line.lower() and "done" in line.lower():
                    # Extract done count: "27 emails — 23 Done"
                    m = re.search(r'(\d+)\s+Done', line, re.IGNORECASE)
                    if m:
                        data["emails_processed"] += int(m.group(1))
                elif "_ERROR" in line or "ERROR" in line:
                    data["errors"].append(line[:200])

        current += timedelta(days=1)

    return data


def collect_done_items(week_start: datetime, week_end: datetime) -> list[dict]:
    """List tasks completed this week."""
    items = []
    if not DONE_DIR.exists():
        return items

    for f in DONE_DIR.glob("*.md"):
        if f.name == ".gitkeep":
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if week_start <= mtime <= week_end:
                content = f.read_text(encoding="utf-8", errors="ignore")
                # Extract subject from frontmatter or first heading
                subject_m = re.search(r'^subject:\s*(.+)$', content, re.MULTILINE)
                type_m    = re.search(r'^type:\s*(.+)$', content, re.MULTILINE)
                items.append({
                    "name": f.name,
                    "subject": subject_m.group(1).strip() if subject_m else f.stem,
                    "type": type_m.group(1).strip() if type_m else "task",
                })
        except Exception:
            pass
    return items


def collect_pending_items() -> list[dict]:
    """List items currently waiting for approval."""
    items = []
    if not PENDING_DIR.exists():
        return items

    for f in PENDING_DIR.glob("*.md"):
        if f.name == ".gitkeep":
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            subject_m = re.search(r'^subject:\s*(.+)$', content, re.MULTILINE)
            type_m    = re.search(r'^type:\s*(.+)$', content, re.MULTILINE)
            items.append({
                "name": f.name,
                "subject": subject_m.group(1).strip() if subject_m else f.stem,
                "type": type_m.group(1).strip() if type_m else "item",
            })
        except Exception:
            pass
    return items


def collect_business_goals() -> dict:
    """Read current targets from Business_Goals.md."""
    if not GOALS_FILE.exists():
        return {}

    content = GOALS_FILE.read_text(encoding="utf-8", errors="ignore")

    # Revenue target
    rev_m = re.search(r'Monthly goal:\s*\$?([\d,]+)', content)
    mtd_m = re.search(r'Current MTD:\s*\$?([\d,]+)', content)

    # Active projects — only from the "### Active Projects" section
    projects_match = re.search(
        r'### Active Projects\n(.*?)(?:\n###|\Z)', content, re.DOTALL
    )
    projects = []
    if projects_match:
        section = projects_match.group(1)
        if "Add your" not in section and "No active" not in section:
            projects = re.findall(r'^\s*[-*]\s+(.+)$', section, re.MULTILINE)
            projects = [p.strip() for p in projects if len(p.strip()) > 3]

    return {
        "monthly_target": rev_m.group(1) if rev_m else "0",
        "revenue_mtd": mtd_m.group(1) if mtd_m else "0",
        "active_projects": projects,
        "raw": content[:2000],
    }


def collect_odoo_data() -> dict:
    """Try to get financial data from Odoo via XML-RPC."""
    data = {"available": False}

    odoo_url = os.getenv("ODOO_URL", "")
    if not odoo_url:
        return data

    try:
        import xmlrpc.client

        db       = os.getenv("ODOO_DB", "odoo")
        user     = os.getenv("ODOO_USER", "admin")
        password = os.getenv("ODOO_PASSWORD", "admin")

        common  = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
        uid     = common.authenticate(db, user, password, {})
        if not uid:
            return data

        models = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/object", allow_none=True)

        # Get invoices from this week
        week_start, week_end = get_week_range()
        date_from = week_start.strftime("%Y-%m-%d")
        date_to   = week_end.strftime("%Y-%m-%d")

        invoices = models.execute_kw(
            db, uid, password,
            "account.move", "search_read",
            [[
                ["move_type", "in", ["out_invoice", "out_refund"]],
                ["invoice_date", ">=", date_from],
                ["invoice_date", "<=", date_to],
            ]],
            {"fields": ["name", "partner_id", "amount_total", "state", "invoice_date"], "limit": 50}
        )

        # Get expenses
        expenses = models.execute_kw(
            db, uid, password,
            "account.move", "search_read",
            [[
                ["move_type", "in", ["in_invoice", "in_refund"]],
                ["invoice_date", ">=", date_from],
                ["invoice_date", "<=", date_to],
            ]],
            {"fields": ["name", "partner_id", "amount_total", "state"], "limit": 50}
        )

        total_revenue  = sum(i.get("amount_total", 0) for i in invoices if i.get("state") == "posted")
        total_expenses = sum(e.get("amount_total", 0) for e in expenses if e.get("state") == "posted")

        data = {
            "available": True,
            "invoices_count": len(invoices),
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "net_profit": total_revenue - total_expenses,
            "invoices": [
                {
                    "name": i.get("name", ""),
                    "client": i.get("partner_id", ["", "Unknown"])[1] if i.get("partner_id") else "Unknown",
                    "amount": i.get("amount_total", 0),
                    "status": i.get("state", ""),
                }
                for i in invoices[:10]
            ],
        }

    except Exception as e:
        logger.warning(f"Odoo not available: {e}")
        data = {"available": False, "error": str(e)}

    return data


def collect_social_media_posts(week_start: datetime, week_end: datetime) -> dict:
    """Count social media posts this week."""
    posts = {"linkedin": [], "facebook": []}

    for folder in [VAULT_PATH / "Approved", DONE_DIR]:
        if not folder.exists():
            continue
        for f in folder.glob("LINKEDIN_*.md"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if week_start <= mtime <= week_end:
                    posts["linkedin"].append(f.stem)
            except Exception:
                pass
        for f in folder.glob("FACEBOOK_*.md"):
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if week_start <= mtime <= week_end:
                    posts["facebook"].append(f.stem)
            except Exception:
                pass

    return posts


# ── Report Builder ──────────────────────────────────────────────────────────────

def build_data_summary(
    logs: dict,
    done_items: list,
    pending_items: list,
    goals: dict,
    odoo: dict,
    social: dict,
    week_start: datetime,
    week_end: datetime,
) -> str:
    """Build a structured data summary to send to Claude."""

    lines = [
        f"# Weekly Business Data — {week_start.strftime('%b %d')} to {week_end.strftime('%b %d, %Y')}",
        "",
        "## Activity This Week",
        f"- Total system events logged: {logs['total_events']}",
        f"- Emails processed/sorted: {logs['emails_processed']}",
        f"- Emails sent: {logs['emails_sent']}",
        f"- LinkedIn posts published: {len(social['linkedin'])} ({', '.join(social['linkedin']) if social['linkedin'] else 'none'})",
        f"- Facebook posts published: {len(social['facebook'])} ({', '.join(social['facebook']) if social['facebook'] else 'none'})",
        f"- Tasks completed: {len(done_items)}",
        "",
        "## Completed Tasks",
    ]
    if done_items:
        for item in done_items[:20]:
            lines.append(f"- [{item['type']}] {item['subject']}")
    else:
        lines.append("- No tasks completed this week")

    lines += [
        "",
        "## Pending Approval",
        f"Total pending: {len(pending_items)}",
    ]
    for item in pending_items[:10]:
        lines.append(f"- [{item['type']}] {item['subject']}")

    lines += [
        "",
        "## Financial Overview",
    ]
    if odoo.get("available"):
        lines += [
            f"- Invoices this week: {odoo['invoices_count']}",
            f"- Revenue (posted): ${odoo['total_revenue']:,.2f}",
            f"- Expenses (posted): ${odoo['total_expenses']:,.2f}",
            f"- Net profit: ${odoo['net_profit']:,.2f}",
            "",
            "### Invoice Details",
        ]
        for inv in odoo.get("invoices", []):
            lines.append(f"- {inv['name']} | {inv['client']} | ${inv['amount']:,.2f} | {inv['status']}")
    else:
        lines += [
            f"- Monthly revenue target: ${goals.get('monthly_target', '0')}",
            f"- Revenue MTD: ${goals.get('revenue_mtd', '0')}",
            "- Note: Odoo not connected — data from Business_Goals.md only",
        ]

    lines += [
        "",
        "## Business Goals",
    ]
    projects = goals.get("active_projects", [])
    if projects:
        lines.append("Active projects:")
        for p in projects[:10]:
            lines.append(f"- {p}")
    else:
        lines.append("- No active projects listed in Business_Goals.md")

    lines += [
        "",
        "## System Errors This Week",
    ]
    errors = logs.get("errors", [])
    if errors:
        for e in errors[:10]:
            lines.append(f"- {e}")
    else:
        lines.append("- No errors recorded")

    return "\n".join(lines)


def generate_briefing(data_summary: str, goals: dict) -> str:
    """Call Claude API to generate the CEO briefing."""
    if not ANTHROPIC_AVAILABLE:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""You are a Chief of Staff preparing a Weekly CEO Briefing for a solo entrepreneur / small business owner.

Here is the raw data from all business systems this week:

{data_summary}

Write a concise, actionable Weekly CEO Briefing in Markdown format. Include these sections:

## 📊 Weekly Snapshot
A 2-3 sentence executive summary of the week.

## ✅ Wins This Week
Bullet points of what went well (be specific, reference actual data).

## ⚠️ Bottlenecks & Issues
What's blocking progress? Reference actual errors or pending items.

## 💰 Revenue & Finance
Brief financial status vs targets. Mention if targets aren't set yet and suggest setting them.

## 📣 Content & Visibility
LinkedIn, Facebook, and social media performance this week.

## 🎯 Top 3 Priorities for Next Week
Specific, actionable. Based on the bottlenecks and goals.

## 💡 AI Insight
One surprising observation or recommendation from the data that the owner might have missed.

---
Rules:
- Be direct and specific — use actual numbers from the data
- Don't pad with generic business advice
- If something is missing (like revenue targets), flag it clearly
- Keep the whole briefing under 600 words
- Write in English
- Use emojis for section headers only (already in the template above)

Write the briefing now:"""

    logger.info("Generating CEO briefing with Claude API...")

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip()


# ── Save & Notify ───────────────────────────────────────────────────────────────

def save_briefing(briefing_text: str, data_summary: str, week_start: datetime) -> Path:
    """Save the briefing to vault."""
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"CEO_BRIEFING_{week_start.strftime('%Y-%m-%d')}.md"
    filepath = BRIEFINGS_DIR / filename

    now_iso = datetime.now(timezone.utc).isoformat()

    content = f"""---
type: ceo_briefing
week_start: {week_start.strftime('%Y-%m-%d')}
generated: {now_iso}
generated_by: AI Employee (CEO Briefing Scheduler)
---

# CEO Weekly Briefing — Week of {week_start.strftime('%B %d, %Y')}

> Generated by AI Employee on {datetime.now().strftime('%A, %B %d, %Y at %H:%M')}

---

{briefing_text}

---

## 📋 Raw Data Used

<details>
<summary>Click to expand raw data</summary>

```
{data_summary}
```

</details>
"""

    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Saved: {filepath}")
    return filepath


def update_dashboard(briefing_path: Path):
    """Add briefing to dashboard activity log."""
    if not DASHBOARD_FILE.exists():
        return

    dash = DASHBOARD_FILE.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc)
    row = f"| {now.strftime('%Y-%m-%d %H:%M:%S')} | CEO Briefing generated: {briefing_path.name} |"

    dash = dash.replace(
        "| Time (UTC)          | Action                                      |",
        "| Time (UTC)          | Action                                      |\n" + row,
    )
    DASHBOARD_FILE.write_text(dash, encoding="utf-8")


def log_event(event_type: str, details: str):
    today = datetime.now().strftime("%Y-%m-%d")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = f"[{datetime.now(timezone.utc).isoformat()}] [CEOBriefing] {event_type}: {details}\n"
    with open(LOGS_DIR / f"{today}.log", "a", encoding="utf-8") as f:
        f.write(entry)


def send_briefing_email(briefing_text: str, week_start: datetime):
    """Email the briefing to the owner."""
    if not EMAIL_FROM or not EMAIL_APP_PASSWORD:
        logger.warning("Email not configured — skipping email send")
        return

    subject = f"CEO Weekly Briefing — Week of {week_start.strftime('%B %d, %Y')}"

    # Convert markdown to plain text (basic)
    plain = re.sub(r'#+\s+', '', briefing_text)
    plain = re.sub(r'\*\*(.+?)\*\*', r'\1', plain)
    plain = re.sub(r'`(.+?)`', r'\1', plain)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_FROM  # Send to yourself

    # Plain text part
    msg.attach(MIMEText(plain, "plain"))

    # HTML part (simple markdown-to-html)
    html_body = briefing_text
    html_body = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html_body, flags=re.MULTILINE)
    html_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_body)
    html_body = re.sub(r'^- (.+)$', r'<li>\1</li>', html_body, flags=re.MULTILINE)
    html_body = html_body.replace('\n\n', '</p><p>').replace('\n', '<br>')
    html_full = f"<html><body><p>{html_body}</p></body></html>"
    msg.attach(MIMEText(html_full, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_FROM, msg.as_string())
        logger.info(f"Briefing emailed to {EMAIL_FROM}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")


# ── Main ────────────────────────────────────────────────────────────────────────

def already_generated_this_week(week_start: datetime) -> bool:
    """Check if a briefing was already generated for this week."""
    filepath = BRIEFINGS_DIR / f"CEO_BRIEFING_{week_start.strftime('%Y-%m-%d')}.md"
    return filepath.exists()


def main():
    parser = argparse.ArgumentParser(description="CEO Weekly Business Briefing Generator")
    parser.add_argument("--force",   action="store_true", help="Force run even if not Monday / already generated")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--email",   action="store_true", help="Email the briefing after generating")
    args = parser.parse_args()

    today_name = datetime.now().strftime("%A")
    logger.info(f"CEO Briefing scheduler running — today is {today_name}")

    week_start, week_end = get_week_range()
    logger.info(f"Week: {week_start.strftime('%Y-%m-%d')} → {week_end.strftime('%Y-%m-%d')}")

    # Only run on Mondays (unless forced)
    if not args.force and today_name != "Monday":
        logger.info(f"CEO Briefing runs on Mondays — today is {today_name}. Use --force to override.")
        return

    # Skip if already generated this week
    if not args.force and already_generated_this_week(week_start):
        logger.info("CEO Briefing already generated for this week — skipping")
        return

    # ── Collect data ────────────────────────────────────────────────────────────
    logger.info("Collecting data from all sources...")

    logs        = collect_logs_data(week_start, week_end)
    done_items  = collect_done_items(week_start, week_end)
    pending     = collect_pending_items()
    goals       = collect_business_goals()
    odoo        = collect_odoo_data()
    social      = collect_social_media_posts(week_start, week_end)

    logger.info(f"  Events:   {logs['total_events']}")
    logger.info(f"  Done:     {len(done_items)} items")
    logger.info(f"  Pending:  {len(pending)} items")
    logger.info(f"  Odoo:     {'connected' if odoo.get('available') else 'not available'}")
    logger.info(f"  LinkedIn: {len(social['linkedin'])} posts")
    logger.info(f"  Facebook: {len(social['facebook'])} posts")

    # ── Build data summary ──────────────────────────────────────────────────────
    data_summary = build_data_summary(
        logs, done_items, pending, goals, odoo, social, week_start, week_end
    )

    if args.dry_run:
        logger.info("[DRY RUN] Data summary:")
        print("\n" + data_summary + "\n")
        logger.info("[DRY RUN] Would generate briefing — skipping Claude API call")
        return

    # ── Generate briefing with Claude ───────────────────────────────────────────
    try:
        briefing_text = generate_briefing(data_summary, goals)
        logger.info(f"Briefing generated ({len(briefing_text)} chars)")
    except Exception as e:
        logger.error(f"Failed to generate briefing: {e}")
        log_event("BRIEFING_ERROR", str(e))
        return

    # ── Save to vault ───────────────────────────────────────────────────────────
    filepath = save_briefing(briefing_text, data_summary, week_start)
    update_dashboard(filepath)
    log_event("BRIEFING_GENERATED", filepath.name)

    # ── Email (optional) ────────────────────────────────────────────────────────
    if args.email:
        send_briefing_email(briefing_text, week_start)

    # ── Print preview ───────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print(f"  CEO WEEKLY BRIEFING — {week_start.strftime('%B %d, %Y')}")
    print("═" * 60)
    print(briefing_text[:1500])
    if len(briefing_text) > 1500:
        print(f"\n... [{len(briefing_text) - 1500} more chars] ...")
    print("═" * 60)
    print(f"\nSaved: {filepath}")
    print(f"Open in Obsidian: Briefings/{filepath.name}")


if __name__ == "__main__":
    main()
