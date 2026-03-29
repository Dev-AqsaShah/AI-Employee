"""
linkedin_watcher.py — LinkedIn Auto-Poster for AI Employee (Silver Tier)

Uses Playwright to:
  1. Watch /Approved/ folder for LINKEDIN_*.md files
  2. Open LinkedIn in browser
  3. Post the approved content
  4. Move file to /Done/

Setup:
  1. pip install playwright
  2. playwright install chromium
  3. Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env
  4. First run saves session to avoid repeated logins

Usage:
    python watchers/linkedin_watcher.py              # Watch mode
    python watchers/linkedin_watcher.py --post-now   # Post all approved immediately
    python watchers/linkedin_watcher.py --dry-run    # Test without posting
"""

import os
import sys
import re
import time
import shutil
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

# ── Playwright ─────────────────────────────────────────────────────────────────
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [LinkedInWatcher] %(levelname)s: %(message)s",
)
logger = logging.getLogger("LinkedInWatcher")

# ── Config ─────────────────────────────────────────────────────────────────────
LINKEDIN_EMAIL    = os.getenv("LINKEDIN_EMAIL", "")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD", "")
VAULT_PATH        = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
SESSION_PATH      = Path(os.getenv("LINKEDIN_SESSION_PATH", "credentials/linkedin_session"))
DRY_RUN           = os.getenv("DRY_RUN", "false").lower() == "true"

APPROVED_DIR = VAULT_PATH / "Approved"
DONE_DIR     = VAULT_PATH / "Done"
LOGS_DIR     = VAULT_PATH / "Logs"


# ── Post content extractor ─────────────────────────────────────────────────────

def extract_post_content(filepath: Path) -> str:
    """Extract the LinkedIn post body from an approved .md file."""
    content = filepath.read_text(encoding="utf-8")

    # Remove YAML frontmatter
    content = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)

    # Remove markdown headings
    content = re.sub(r"^#{1,6}\s+.*$", "", content, flags=re.MULTILINE)

    # Remove approval instruction lines
    content = re.sub(r"^.*(?:Pending_Approval|Approved|Rejected|Move this|approval).*$",
                     "", content, flags=re.MULTILINE | re.IGNORECASE)

    # Clean up extra blank lines
    content = re.sub(r"\n{3,}", "\n\n", content).strip()

    return content


# ── LinkedIn Poster ────────────────────────────────────────────────────────────

class LinkedInPoster:
    """Posts content to LinkedIn using Playwright browser automation."""

    def __init__(self):
        self.session_path = str(SESSION_PATH)
        SESSION_PATH.mkdir(parents=True, exist_ok=True)

    def _log(self, action: str, details: str):
        today = datetime.now().strftime("%Y-%m-%d")
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        entry = f"[{datetime.now(timezone.utc).isoformat()}] [LinkedIn] {action}: {details}\n"
        with open(LOGS_DIR / f"{today}.log", "a", encoding="utf-8") as f:
            f.write(entry)

    def post(self, content: str) -> dict:
        """Open LinkedIn and create a post with the given content."""
        if not PLAYWRIGHT_AVAILABLE:
            return {"status": "error", "message": "Playwright not installed. Run: pip install playwright && playwright install chromium"}

        if DRY_RUN:
            logger.info(f"[DRY RUN] Would post to LinkedIn:\n{content[:100]}...")
            self._log("POST_DRY_RUN", content[:80])
            return {"status": "dry_run", "message": "DRY RUN — post not sent"}

        if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
            return {"status": "error", "message": "LINKEDIN_EMAIL and LINKEDIN_PASSWORD not set in .env"}

        # Session state file for saving login cookies
        session_file = SESSION_PATH / "state.json"

        try:
            with sync_playwright() as p:
                # Launch system Chrome via channel (most reliable on Windows)
                logger.info("Launching Chrome browser...")
                browser = p.chromium.launch(
                    channel="chrome",
                    headless=False,
                    args=["--start-maximized"],
                )

                # Load saved session if exists
                if session_file.exists():
                    context = browser.new_context(
                        storage_state=str(session_file),
                        viewport={"width": 1280, "height": 800},
                    )
                    logger.info("Loaded saved LinkedIn session.")
                else:
                    context = browser.new_context(
                        viewport={"width": 1280, "height": 800},
                    )
                    logger.info("No saved session — will login fresh.")

                page = context.new_page()

                # ── Login if needed ────────────────────────────────────────────
                page.goto("https://www.linkedin.com/feed/", wait_until="commit", timeout=60000)
                time.sleep(5)

                if "login" in page.url or "authwall" in page.url:
                    logger.info("Not logged in — performing login...")
                    result = self._login(page)
                    if not result:
                        browser.close()
                        return {"status": "error", "message": "LinkedIn login failed"}

                # Save session after login
                context.storage_state(path=str(session_file))
                logger.info("Session saved.")

                # ── Create post ────────────────────────────────────────────────
                logger.info("Going to LinkedIn feed to open post composer...")
                page.goto("https://www.linkedin.com/feed/", timeout=60000)
                page.wait_for_load_state("domcontentloaded")
                time.sleep(5)
                page.screenshot(path="debug_screenshots/li_post_new.png")

                # Click "Start a post" button in the feed share box
                start_post_clicked = False
                for sel in [
                    "button.share-box-feed-entry__trigger",
                    "button[aria-label='Start a post']",
                    "[data-control-name='share.sharebox_trigger']",
                    ".share-box-feed-entry__top-bar button",
                    ".share-creation-state__trigger",
                ]:
                    try:
                        btn = page.wait_for_selector(sel, timeout=5000)
                        if btn:
                            btn.click()
                            logger.info(f"Clicked 'Start a post' with selector: {sel}")
                            start_post_clicked = True
                            time.sleep(3)
                            break
                    except Exception:
                        continue

                if not start_post_clicked:
                    # Fallback: click by visible text
                    try:
                        page.get_by_text("Start a post").first.click(timeout=5000)
                        start_post_clicked = True
                        logger.info("Clicked 'Start a post' via text search")
                        time.sleep(3)
                    except Exception:
                        pass

                if not start_post_clicked:
                    page.screenshot(path="debug_screenshots/li_no_start_post.png")
                    raise RuntimeError("Could not find 'Start a post' button")

                page.screenshot(path="debug_screenshots/li_1_after_click.png")
                time.sleep(3)
                page.screenshot(path="debug_screenshots/li_2_after_wait.png")

                # Type the post content in the modal editor
                editor = None

                # Try get_by_placeholder first (most reliable)
                try:
                    loc = page.get_by_placeholder("What do you want to talk about?")
                    loc.wait_for(timeout=8000)
                    editor = loc
                    logger.info("Found editor via placeholder text")
                except Exception:
                    pass

                # Fallback: any contenteditable inside the modal
                if not editor:
                    try:
                        loc = page.locator("[contenteditable='true']").first
                        loc.wait_for(timeout=5000)
                        editor = loc
                        logger.info("Found editor via contenteditable locator")
                    except Exception:
                        pass

                # Last resort: JavaScript click on contenteditable
                if not editor:
                    try:
                        page.evaluate("document.querySelector('[contenteditable]').click()")
                        page.keyboard.type(content, delay=20)
                        time.sleep(1)
                        logger.info("Typed content via JS click fallback")
                        editor = True  # Mark as handled
                    except Exception:
                        pass

                if not editor:
                    page.screenshot(path="debug_screenshots/li_no_editor.png")
                    raise RuntimeError("Could not find post editor — LinkedIn may have changed their UI")

                if editor is not True:
                    editor.click()
                    time.sleep(1)
                    page.keyboard.type(content, delay=20)
                    time.sleep(1)

                # Click Post button
                posted = False
                for selector in [
                    ("role", "button", "Post"),
                    ("css",  "button.share-actions__primary-action", None),
                    ("css",  "button[aria-label='Post']",            None),
                    ("css",  "button.artdeco-button--primary",       None),
                ]:
                    try:
                        kind = selector[0]
                        if kind == "role":
                            page.get_by_role("button", name=selector[2]).last.click(timeout=6000)
                        elif kind == "css":
                            page.wait_for_selector(selector[1], timeout=6000)
                            page.click(selector[1])
                        posted = True
                        break
                    except Exception:
                        continue

                if not posted:
                    raise RuntimeError("Could not find Post submit button")

                time.sleep(3)
                logger.info("Post published successfully!")
                self._log("POST_SUCCESS", content[:80])
                browser.close()
                return {"status": "success", "message": "Post published on LinkedIn"}

        except Exception as e:
            logger.error(f"LinkedIn post failed: {e}")
            self._log("POST_ERROR", str(e)[:200])
            return {"status": "error", "message": str(e)[:200]}

    def _login(self, page) -> bool:
        """Perform LinkedIn login."""
        try:
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            time.sleep(2)

            page.fill("#username", LINKEDIN_EMAIL)
            page.fill("#password", LINKEDIN_PASSWORD)
            page.click("button[type='submit']")

            time.sleep(4)

            # Check if login succeeded
            if "feed" in page.url or "mynetwork" in page.url:
                logger.info("LinkedIn login successful. Session saved.")
                return True

            # 2FA or verification needed
            if "checkpoint" in page.url or "challenge" in page.url:
                logger.warning("LinkedIn requires verification (2FA). Complete it in the browser window.")
                input("Press Enter after completing verification in the browser...")
                return True

            logger.error(f"Login failed. Current URL: {page.url}")
            return False

        except Exception as e:
            logger.error(f"Login error: {e}")
            return False


# ── Watcher ────────────────────────────────────────────────────────────────────

class LinkedInWatcher(BaseWatcher):
    """
    Watches /Approved/ for LINKEDIN_*.md files and posts them.
    """

    def __init__(self, vault_path: str, check_interval: int = 30):
        super().__init__(vault_path, check_interval=check_interval)
        self.approved_dir = VAULT_PATH / "Approved"
        self.done_dir     = VAULT_PATH / "Done"
        self.poster       = LinkedInPoster()
        self._posted: set = set()

    def check_for_updates(self) -> list:
        """Find approved LinkedIn post files."""
        return [
            f for f in self.approved_dir.glob("LINKEDIN_*.md")
            if str(f) not in self._posted
        ]

    def create_action_file(self, item: Path) -> Path:
        """Post to LinkedIn and move file to Done."""
        content = extract_post_content(item)

        if not content.strip():
            logger.warning(f"Empty post content in {item.name} — skipping")
            return item

        logger.info(f"Posting: {item.name}")
        logger.info(f"Preview: {content[:80]}...")

        result = self.poster.post(content)

        if result["status"] in ("success", "dry_run"):
            # Update file status and move to Done
            raw = item.read_text(encoding="utf-8")
            raw = raw.replace("status: pending_approval", "status: posted")
            raw += f"\n\n## Posted [{datetime.now(timezone.utc).isoformat()}]\n- **Result:** {result['message']}\n"

            done_path = self.done_dir / item.name
            done_path.write_text(raw, encoding="utf-8")
            item.unlink()

            logger.info(f"Moved to Done: {item.name}")
            self.log_event("LINKEDIN_POSTED", item.name)

            # Update dashboard
            self._update_dashboard(item.name, result["status"])
        else:
            logger.error(f"Post failed: {result['message']}")
            self.log_event("LINKEDIN_ERROR", result["message"])

        self._posted.add(str(item))
        return item

    def _update_dashboard(self, filename: str, status: str):
        dashboard = VAULT_PATH / "Dashboard.md"
        if not dashboard.exists():
            return
        dash = dashboard.read_text(encoding="utf-8")
        row = f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | LinkedIn post {status}: {filename} |"
        dash = dash.replace(
            "| Time (UTC)          | Action                                      |",
            "| Time (UTC)          | Action                                      |\n" + row
        )
        dashboard.write_text(dash, encoding="utf-8")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI Employee — LinkedIn Watcher (Silver Tier)")
    parser.add_argument("--vault",      default=os.getenv("VAULT_PATH", "AI_Employee_Vault"))
    parser.add_argument("--interval",   type=int, default=30)
    parser.add_argument("--post-now",   action="store_true", help="Post all approved files immediately")
    parser.add_argument("--dry-run",    action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
        global DRY_RUN
        DRY_RUN = True

    watcher = LinkedInWatcher(vault_path=args.vault, check_interval=args.interval)

    if args.post_now:
        # One-shot: post all approved files now
        items = watcher.check_for_updates()
        logger.info(f"Found {len(items)} approved post(s)")
        for item in items:
            watcher.create_action_file(item)
        logger.info("Done.")
    else:
        # Watch mode
        watcher.run()


if __name__ == "__main__":
    main()
