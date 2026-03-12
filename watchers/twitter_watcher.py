"""
twitter_watcher.py — Twitter/X Auto-Poster for AI Employee (Gold Tier)

Uses Playwright browser automation (NO API needed).
Watches Approved/ for TWITTER_*.md files and posts to X (Twitter).

Setup:
  1. Set in .env:
       TWITTER_USERNAME=your_twitter_username
       TWITTER_PASSWORD=your_twitter_password

Usage:
    python watchers/twitter_watcher.py            # Watch mode
    python watchers/twitter_watcher.py --setup    # Save login session (run once)
    python watchers/twitter_watcher.py --post-now # Post all approved immediately
    python watchers/twitter_watcher.py --dry-run  # Test without posting
"""

import os
import re
import sys
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TwitterWatcher] %(levelname)s: %(message)s",
)
logger = logging.getLogger("TwitterWatcher")

# ── Config ───────────────────────────────────────────────────────────────────────
TWITTER_USERNAME = os.getenv("TWITTER_USERNAME", "")
TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD", "")
VAULT_PATH       = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
SESSION_PATH     = Path(os.getenv("TWITTER_SESSION_PATH", "credentials/twitter_session"))
DRY_RUN          = os.getenv("DRY_RUN", "false").lower() == "true"

APPROVED_DIR = VAULT_PATH / "Approved"
DONE_DIR     = VAULT_PATH / "Done"
LOGS_DIR     = VAULT_PATH / "Logs"

TWITTER_CHAR_LIMIT = 280


def extract_post_content(filepath: Path) -> str:
    content = filepath.read_text(encoding="utf-8")
    content = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
    content = re.sub(r"^#{1,6}\s+.*$", "", content, flags=re.MULTILINE)
    content = re.sub(
        r"^.*(?:Pending_Approval|Approved|Rejected|Move this|approval|APPROVE|EDIT|REJECT|Instructions|Drafted by).*$",
        "", content, flags=re.MULTILINE | re.IGNORECASE
    )
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    # Twitter/X limit: 280 chars
    if len(content) > TWITTER_CHAR_LIMIT:
        content = content[:TWITTER_CHAR_LIMIT - 3] + "..."
    return content


class TwitterPoster:
    def __init__(self):
        SESSION_PATH.mkdir(parents=True, exist_ok=True)

    def _log(self, action: str, details: str):
        today = datetime.now().strftime("%Y-%m-%d")
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        entry = f"[{datetime.now(timezone.utc).isoformat()}] [Twitter] {action}: {details}\n"
        with open(LOGS_DIR / f"{today}.log", "a", encoding="utf-8") as f:
            f.write(entry)

    def setup_session(self):
        """Open browser for manual Twitter/X login. Run once."""
        if not PLAYWRIGHT_AVAILABLE:
            print("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return False

        session_file = SESSION_PATH / "state.json"
        print("\n" + "="*50)
        print("TWITTER/X SESSION SETUP")
        print("="*50)
        print("Browser khulega — X (Twitter) pe manually login karo.")
        print("Login ke baad terminal pe Enter dabaو — session save ho jayegi.")
        print("="*50 + "\n")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()
            page.goto("https://x.com/login", wait_until="commit", timeout=60000)
            print("X (Twitter) login karo...")
            input("\nLogin complete hone ke baad yahan Enter dabaо: ")
            context.storage_state(path=str(session_file))
            browser.close()

        print(f"\nSession saved: {session_file}")
        return True

    def post(self, content: str) -> dict:
        if not PLAYWRIGHT_AVAILABLE:
            return {"status": "error", "message": "Playwright not installed"}

        if DRY_RUN:
            logger.info(f"[DRY RUN] Would tweet:\n{content[:100]}...")
            self._log("POST_DRY_RUN", content[:80])
            return {"status": "dry_run", "message": "DRY RUN — tweet not sent"}

        session_file = SESSION_PATH / "state.json"
        if not session_file.exists():
            return {"status": "error", "message": "No saved session. Run: python watchers/twitter_watcher.py --setup"}

        debug_dir = Path("debug_screenshots")
        debug_dir.mkdir(exist_ok=True)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                context = browser.new_context(
                    storage_state=str(session_file),
                    viewport={"width": 1280, "height": 800},
                )
                page = context.new_page()

                logger.info("Opening X (Twitter)...")
                page.goto("https://x.com/home", wait_until="commit", timeout=60000)
                time.sleep(4)

                if "login" in page.url or "signin" in page.url:
                    browser.close()
                    return {"status": "error", "message": "Session expired. Run --setup again"}

                page.screenshot(path=str(debug_dir / "tw_1_home.png"))
                logger.info("Logged in. Finding tweet composer...")

                # Find compose tweet area
                editor = None
                for sel in [
                    "[data-testid='tweetTextarea_0']",
                    "div[aria-label='Post text'][contenteditable='true']",
                    "div[data-offset-key][contenteditable='true']",
                    "div[role='textbox'][contenteditable='true']",
                    "div[aria-placeholder='What is happening?!']",
                    "div[contenteditable='true']",
                ]:
                    try:
                        el = page.wait_for_selector(sel, timeout=5000)
                        if el and el.is_visible():
                            editor = el
                            logger.info(f"Found composer: {sel}")
                            break
                    except Exception:
                        continue

                if not editor:
                    # Try clicking "What is happening?!" placeholder
                    try:
                        page.get_by_placeholder("What is happening?!").click(timeout=4000)
                        time.sleep(2)
                        for sel in ["div[data-testid='tweetTextarea_0']", "div[contenteditable='true']"]:
                            try:
                                editor = page.wait_for_selector(sel, timeout=3000)
                                if editor and editor.is_visible():
                                    break
                                editor = None
                            except Exception:
                                continue
                    except Exception:
                        pass

                if not editor:
                    page.screenshot(path=str(debug_dir / "tw_error_no_composer.png"))
                    raise RuntimeError("Could not find tweet composer. Check tw_1_home.png")

                # Type tweet
                editor.click()
                time.sleep(1)
                page.keyboard.type(content, delay=20)
                time.sleep(2)

                page.screenshot(path=str(debug_dir / "tw_2_typed.png"))
                logger.info(f"Typed tweet ({len(content)} chars)")

                # Click Post / Tweet button
                posted = False
                for btn_name in ["Post", "Tweet"]:
                    try:
                        btns = page.get_by_role("button", name=btn_name).all()
                        for btn in btns:
                            if btn.is_visible() and btn.is_enabled():
                                btn.click()
                                posted = True
                                logger.info(f"Clicked: '{btn_name}'")
                                break
                        if posted:
                            break
                    except Exception:
                        continue

                # CSS fallback
                if not posted:
                    for sel in [
                        "[data-testid='tweetButtonInline']",
                        "[data-testid='tweetButton']",
                    ]:
                        try:
                            el = page.wait_for_selector(sel, timeout=3000)
                            if el and el.is_visible() and el.is_enabled():
                                el.click()
                                posted = True
                                break
                        except Exception:
                            continue

                if not posted:
                    page.screenshot(path=str(debug_dir / "tw_error_no_post_btn.png"))
                    raise RuntimeError("Could not find Post button")

                time.sleep(4)
                logger.info("Tweet published!")
                self._log("POST_SUCCESS", f"chars={len(content)}")
                browser.close()
                return {"status": "success", "message": "Tweet published on X (Twitter)"}

        except Exception as e:
            logger.error(f"Twitter post failed: {e}")
            self._log("POST_ERROR", str(e)[:200])
            return {"status": "error", "message": str(e)[:200]}


class TwitterWatcher(BaseWatcher):
    def __init__(self, vault_path: str, check_interval: int = 30):
        super().__init__(vault_path, check_interval=check_interval)
        self.approved_dir = VAULT_PATH / "Approved"
        self.done_dir     = VAULT_PATH / "Done"
        self.poster       = TwitterPoster()
        self._posted: set = set()

    def check_for_updates(self) -> list:
        return [
            f for f in self.approved_dir.glob("TWITTER_*.md")
            if str(f) not in self._posted
        ]

    def create_action_file(self, item: Path) -> Path:
        content = extract_post_content(item)
        if not content.strip():
            logger.warning(f"Empty content in {item.name} — skipping")
            self._posted.add(str(item))
            return item

        logger.info(f"Tweeting: {item.name}")
        result = self.poster.post(content)

        if result["status"] in ("success", "dry_run"):
            raw = item.read_text(encoding="utf-8")
            raw = raw.replace("status: pending_approval", "status: posted")
            raw += f"\n\n## Posted [{datetime.now(timezone.utc).isoformat()}]\n- **Result:** {result['message']}\n"
            done_path = self.done_dir / item.name
            done_path.write_text(raw, encoding="utf-8")
            item.unlink()
            logger.info(f"Moved to Done: {item.name}")
            self.log_event("TWITTER_POSTED", item.name)
            self._update_dashboard(item.name, result["status"])
        else:
            logger.error(f"Tweet failed: {result['message']}")
            self.log_event("TWITTER_ERROR", result["message"])

        self._posted.add(str(item))
        return item

    def _update_dashboard(self, filename: str, status: str):
        dashboard = VAULT_PATH / "Dashboard.md"
        if not dashboard.exists():
            return
        dash = dashboard.read_text(encoding="utf-8")
        row = f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Twitter post {status}: {filename} |"
        dash = dash.replace(
            "| Time (UTC)          | Action                                      |",
            "| Time (UTC)          | Action                                      |\n" + row
        )
        dashboard.write_text(dash, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="AI Employee — Twitter/X Watcher")
    parser.add_argument("--vault",    default=os.getenv("VAULT_PATH", "AI_Employee_Vault"))
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--post-now", action="store_true")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--setup",    action="store_true", help="Save login session (run once)")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
        global DRY_RUN
        DRY_RUN = True

    if args.setup:
        TwitterPoster().setup_session()
        return

    watcher = TwitterWatcher(vault_path=args.vault, check_interval=args.interval)

    if args.post_now:
        items = watcher.check_for_updates()
        logger.info(f"Found {len(items)} approved tweet(s)")
        for item in items:
            watcher.create_action_file(item)
        logger.info("Done.")
    else:
        watcher.run()


if __name__ == "__main__":
    main()
