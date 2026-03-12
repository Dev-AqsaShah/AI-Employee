"""
twitter_scheduler.py — Autonomous Twitter/X Post Scheduler

Runs daily. On posting days, uses Claude API to draft a tweet
and saves to /Pending_Approval/ for human review.

Posting days: Monday, Wednesday, Friday (by default)
Twitter style: 280 char hard limit, punchy, no fluff

Usage:
    python schedulers/twitter_scheduler.py           # Run for today
    python schedulers/twitter_scheduler.py --force   # Force draft
    python schedulers/twitter_scheduler.py --dry-run # Preview only
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
    format="%(asctime)s [TwitterScheduler] %(levelname)s: %(message)s",
)
logger = logging.getLogger("TwitterScheduler")

VAULT_PATH        = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PENDING_DIR       = VAULT_PATH / "Pending_Approval"
LOGS_DIR          = VAULT_PATH / "Logs"
GOALS_FILE        = VAULT_PATH / "Business_Goals.md"
DONE_DIR          = VAULT_PATH / "Done"

POSTING_DAYS_DEFAULT = ["Monday", "Wednesday", "Friday"]
TWITTER_CHAR_LIMIT   = 280


def read_content_strategy() -> dict:
    if not GOALS_FILE.exists():
        return {}
    content = GOALS_FILE.read_text(encoding="utf-8")
    days_match = re.search(r"twitter_posting_days:\s*(.+)", content)
    posting_days = [d.strip() for d in days_match.group(1).split(",")] if days_match else POSTING_DAYS_DEFAULT
    topics = re.findall(r"^\d+\.\s+(.+)$", content, re.MULTILINE)
    tagline_match = re.search(r"Business Tagline.*?\n\"(.+?)\"", content, re.DOTALL)
    tagline = tagline_match.group(1).strip() if tagline_match else ""
    return {"posting_days": posting_days, "topics": topics, "tagline": tagline}


def is_posting_day(posting_days: list) -> bool:
    return datetime.now().strftime("%A") in posting_days


def already_drafted_today() -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    for folder in [PENDING_DIR, VAULT_PATH / "Approved", DONE_DIR]:
        if folder.exists():
            for f in folder.glob(f"TWITTER_{today}*.md"):
                return True
    return False


def pick_topic(topics: list) -> str:
    if not topics:
        return "AI automation changing how businesses operate"
    day_of_year = datetime.now().timetuple().tm_yday
    # Offset by 1 so Twitter and LinkedIn don't pick the same topic
    return topics[(day_of_year + 1) % len(topics)]


def generate_tweet(strategy: dict, topic: str) -> str:
    if not ANTHROPIC_AVAILABLE or not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set or anthropic not installed")
        return ""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    tagline = strategy.get("tagline", "")

    prompt = f"""Write a tweet about: {topic}

Business tagline: {tagline}

Tweet requirements:
- HARD LIMIT: 280 characters maximum (count carefully)
- Punchy, direct, no filler words
- One clear idea or insight
- Optional: 1-2 relevant hashtags (only if they add value)
- Optional: 1 emoji maximum
- No corporate speak — sound human
- End with a thought-provoking statement or question

Return ONLY the tweet text, nothing else. Verify it is under 280 characters."""

    logger.info(f"Generating tweet about: {topic}")
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    tweet = response.content[0].text.strip()

    # Hard truncate if over limit
    if len(tweet) > TWITTER_CHAR_LIMIT:
        tweet = tweet[:TWITTER_CHAR_LIMIT - 3] + "..."
        logger.warning(f"Tweet truncated to {TWITTER_CHAR_LIMIT} chars")

    return tweet


def save_to_pending(tweet_content: str, topic: str, dry_run: bool = False) -> Path:
    today    = datetime.now().strftime("%Y-%m-%d")
    filename = f"TWITTER_{today}.md"
    filepath = PENDING_DIR / filename

    content = f"""---
type: twitter_post
topic: {topic}
drafted: {datetime.now(timezone.utc).isoformat()}
status: pending_approval
char_count: {len(tweet_content)}
---

# Tweet — {today}

> **Topic:** {topic}
> **Drafted by:** AI Employee (Twitter Scheduler)
> **Char count:** {len(tweet_content)} / {TWITTER_CHAR_LIMIT}

---

## Tweet Content

{tweet_content}

---

## Instructions
- **APPROVE:** Move this file to `/Approved/` — Twitter Watcher will auto-post it
- **EDIT:** Edit the Tweet Content above (keep under {TWITTER_CHAR_LIMIT} chars), then move to `/Approved/`
- **REJECT:** Move this file to `/Rejected/`
"""

    if dry_run:
        logger.info(f"[DRY RUN] Would save: {filename}")
        logger.info(f"[DRY RUN] Tweet preview ({len(tweet_content)} chars):\n{tweet_content}")
        return filepath

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Saved to Pending_Approval: {filename}")
    return filepath


def log_action(action: str, details: str):
    today = datetime.now().strftime("%Y-%m-%d")
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = f"[{datetime.now(timezone.utc).isoformat()}] [TwitterScheduler] {action}: {details}\n"
    with open(LOGS_DIR / f"{today}.log", "a", encoding="utf-8") as f:
        f.write(entry)


def main():
    parser = argparse.ArgumentParser(description="Twitter/X Post Scheduler")
    parser.add_argument("--force",   action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    today_name = datetime.now().strftime("%A")
    logger.info(f"Twitter Scheduler running — today is {today_name}")

    strategy = read_content_strategy()
    posting_days = strategy.get("posting_days", POSTING_DAYS_DEFAULT)

    if not args.force and not is_posting_day(posting_days):
        logger.info(f"Today ({today_name}) is not a posting day — skipping")
        return

    if not args.force and already_drafted_today():
        logger.info("Tweet already drafted today — skipping")
        return

    topics = strategy.get("topics", [])
    topic  = pick_topic(topics)
    logger.info(f"Selected topic: {topic}")

    tweet_content = generate_tweet(strategy, topic)
    if not tweet_content:
        logger.error("Failed to generate tweet — check ANTHROPIC_API_KEY")
        log_action("ERROR", "Failed to generate tweet")
        return

    logger.info(f"Tweet generated ({len(tweet_content)} chars)")
    filepath = save_to_pending(tweet_content, topic, dry_run=args.dry_run)

    if not args.dry_run:
        log_action("TWEET_DRAFTED", f"topic={topic} file={filepath.name} chars={len(tweet_content)}")
        logger.info(f"Done! Review: Pending_Approval/{filepath.name}")
    else:
        logger.info("[DRY RUN] Complete")


if __name__ == "__main__":
    main()
