"""
facebook_scheduler.py — Autonomous Facebook Post Scheduler

Runs daily. Uses Claude API to draft a Facebook post and saves it to
/Pending_Approval/ for human review. The facebook_watcher then auto-posts
when you move the file to /Approved/.

Usage:
    python schedulers/facebook_scheduler.py           # Run once (for today)
    python schedulers/facebook_scheduler.py --force   # Force draft even if not posting day
    python schedulers/facebook_scheduler.py --dry-run # Preview without saving
"""

import os
import re
import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

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
    format="%(asctime)s [FacebookScheduler] %(levelname)s: %(message)s",
)
logger = logging.getLogger("FacebookScheduler")

# ── Config ──────────────────────────────────────────────────────────────────────
VAULT_PATH        = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

PENDING_DIR = VAULT_PATH / "Pending_Approval"
LOGS_DIR    = VAULT_PATH / "Logs"
GOALS_FILE  = VAULT_PATH / "Business_Goals.md"
DONE_DIR    = VAULT_PATH / "Done"

POSTING_DAYS_DEFAULT = ["Tuesday", "Thursday", "Saturday"]


# ── Business Goals Reader ───────────────────────────────────────────────────────

def read_content_strategy() -> dict:
    """Parse Facebook strategy from Business_Goals.md."""
    if not GOALS_FILE.exists():
        return {}

    content = GOALS_FILE.read_text(encoding="utf-8")

    # Try to find Facebook-specific section first, fall back to general
    fb_section_match = re.search(
        r"## Facebook.*?\n(.*?)(?:\n## |\Z)", content, re.DOTALL | re.IGNORECASE
    )
    section = fb_section_match.group(1) if fb_section_match else content

    # Extract posting days
    days_match = re.search(r"posting_days:\s*(.+)", section)
    posting_days = (
        [d.strip() for d in days_match.group(1).split(",")]
        if days_match else POSTING_DAYS_DEFAULT
    )

    # Extract topics list
    topics = re.findall(r"^\d+\.\s+(.+)$", content, re.MULTILINE)

    # Extract brand voice
    voice_match = re.search(r"### Brand Voice\n(.*?)###", content, re.DOTALL)
    brand_voice = voice_match.group(1).strip() if voice_match else ""

    # Extract target audience
    audience_match = re.search(r"### Target Audience\n(.+?)(?:\n\n|###|$)", content, re.DOTALL)
    audience = audience_match.group(1).strip() if audience_match else ""

    # Extract tagline
    tagline_match = re.search(r'Business Tagline.*?\n"(.+?)"', content, re.DOTALL)
    tagline = tagline_match.group(1).strip() if tagline_match else ""

    return {
        "posting_days": posting_days,
        "topics": topics,
        "brand_voice": brand_voice,
        "audience": audience,
        "tagline": tagline,
    }


def is_posting_day(posting_days: list) -> bool:
    today = datetime.now().strftime("%A")
    return today in posting_days


def already_drafted_today() -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    for folder in [PENDING_DIR, VAULT_PATH / "Approved", DONE_DIR]:
        if folder.exists():
            for f in folder.glob(f"FACEBOOK_{today}*.md"):
                return True
    return False


def pick_topic(topics: list) -> str:
    if not topics:
        return "How AI is changing small business operations"
    # Offset by 1 vs LinkedIn so topics don't repeat on same day
    day_of_year = datetime.now().timetuple().tm_yday + 1
    return topics[day_of_year % len(topics)]


# ── Claude API Post Generator ───────────────────────────────────────────────────

def generate_post(strategy: dict, topic: str) -> str:
    """Call Claude API to draft a Facebook post."""
    if not ANTHROPIC_AVAILABLE:
        logger.error("anthropic package not installed. Run: pip install anthropic")
        return ""

    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your-anthropic-api-key-here":
        logger.error("ANTHROPIC_API_KEY not set in .env")
        return ""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    brand_voice = strategy.get("brand_voice", "")
    audience    = strategy.get("audience", "entrepreneurs and small business owners")
    tagline     = strategy.get("tagline", "")

    prompt = f"""Write a Facebook post about: {topic}

Brand voice guidelines:
{brand_voice}

Target audience: {audience}

Business tagline: {tagline}

Requirements:
- Max 500 characters (Facebook performs best at this length)
- Conversational and warm — Facebook is more personal than LinkedIn
- Start with a hook that stops the scroll
- Share a practical tip, story, or insight
- End with a simple call-to-action (comment, like, or share)
- Use 1-2 relevant emojis sparingly — they help on Facebook
- Sound friendly, like a real person talking
- Write in English

Return ONLY the post text, nothing else."""

    logger.info(f"Generating Facebook post about: {topic}")

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text.strip()


# ── Save Draft ──────────────────────────────────────────────────────────────────

def save_to_pending_approval(post_content: str, topic: str, dry_run: bool = False) -> Path:
    today    = datetime.now().strftime("%Y-%m-%d")
    filename = f"FACEBOOK_{today}.md"
    filepath = PENDING_DIR / filename

    content = f"""---
type: facebook_post
topic: {topic}
drafted: {datetime.now(timezone.utc).isoformat()}
status: pending_approval
char_count: {len(post_content)}
---

# Facebook Post — {today}

> **Topic:** {topic}
> **Drafted by:** AI Employee (Facebook Scheduler)
> **Char count:** {len(post_content)} / 500

---

## Post Content

{post_content}

---

## Instructions
- **APPROVE:** Move this file to `/Approved/` — Facebook Watcher will auto-post it
- **EDIT:** Edit the Post Content above, then move to `/Approved/`
- **REJECT:** Move this file to `/Rejected/`
"""

    if dry_run:
        logger.info(f"[DRY RUN] Would save: {filename}")
        logger.info(f"[DRY RUN] Post preview:\n{post_content[:200]}...")
        return filepath

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Saved to Pending_Approval: {filename}")
    return filepath


def log_action(action: str, details: str):
    today = datetime.now().strftime("%Y-%m-%d")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = f"[{datetime.now(timezone.utc).isoformat()}] [FacebookScheduler] {action}: {details}\n"
    with open(LOGS_DIR / f"{today}.log", "a", encoding="utf-8") as f:
        f.write(entry)


# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Facebook Post Scheduler")
    parser.add_argument("--force",   action="store_true", help="Draft even if not posting day")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    args = parser.parse_args()

    today_name = datetime.now().strftime("%A")
    logger.info(f"Facebook Scheduler running — today is {today_name}")

    strategy     = read_content_strategy()
    posting_days = strategy.get("posting_days", POSTING_DAYS_DEFAULT)
    logger.info(f"Posting days: {posting_days}")

    if not args.force and not is_posting_day(posting_days):
        logger.info(f"Today ({today_name}) is not a posting day — skipping")
        logger.info(f"Posting days are: {', '.join(posting_days)}")
        return

    if not args.force and already_drafted_today():
        logger.info("Facebook post already drafted today — skipping")
        return

    topics = strategy.get("topics", [])
    topic  = pick_topic(topics)
    logger.info(f"Selected topic: {topic}")

    post_content = generate_post(strategy, topic)
    if not post_content:
        logger.error("Failed to generate post — check ANTHROPIC_API_KEY in .env")
        log_action("ERROR", "Failed to generate post — API key missing or invalid")
        return

    logger.info(f"Post generated ({len(post_content)} chars)")

    filepath = save_to_pending_approval(post_content, topic, dry_run=args.dry_run)

    if not args.dry_run:
        log_action("POST_DRAFTED", f"topic={topic} file={filepath.name} chars={len(post_content)}")
        logger.info(f"Done! Review and approve: Pending_Approval/{filepath.name}")
    else:
        logger.info("[DRY RUN] Complete — no files saved")


if __name__ == "__main__":
    main()
