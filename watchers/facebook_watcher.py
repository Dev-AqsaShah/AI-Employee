"""
facebook_watcher.py — Facebook Auto-Poster for AI Employee (Gold Tier)

Uses Playwright browser automation (NO API, NO verification needed).
Just logs into Facebook with your email/password and posts to your Page.

Setup:
  1. pip install playwright && playwright install chromium
  2. Set in .env:
       FACEBOOK_EMAIL=your_facebook_email
       FACEBOOK_PASSWORD=your_facebook_password
       FACEBOOK_PAGE_URL=https://www.facebook.com/your_page_name

Usage:
    python watchers/facebook_watcher.py            # Watch mode
    python watchers/facebook_watcher.py --post-now # Post all approved immediately
    python watchers/facebook_watcher.py --dry-run  # Test without posting
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
    format="%(asctime)s [FacebookWatcher] %(levelname)s: %(message)s",
)
logger = logging.getLogger("FacebookWatcher")

# ── Config ──────────────────────────────────────────────────────────────────────
FACEBOOK_EMAIL    = os.getenv("FACEBOOK_EMAIL", "")
FACEBOOK_PASSWORD = os.getenv("FACEBOOK_PASSWORD", "")
FACEBOOK_PAGE_URL = os.getenv("FACEBOOK_PAGE_URL", "")   # e.g. https://www.facebook.com/yourpage
VAULT_PATH        = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
SESSION_PATH      = Path(os.getenv("FACEBOOK_SESSION_PATH", "credentials/facebook_session"))
DRY_RUN           = os.getenv("DRY_RUN", "false").lower() == "true"

APPROVED_DIR = VAULT_PATH / "Approved"
DONE_DIR     = VAULT_PATH / "Done"
LOGS_DIR     = VAULT_PATH / "Logs"


# ── Content extractor ───────────────────────────────────────────────────────────

def extract_post_content(filepath: Path) -> str:
    """Extract post body from approved FACEBOOK_*.md file."""
    content = filepath.read_text(encoding="utf-8")

    # Remove YAML frontmatter
    content = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)

    # Remove markdown headings
    content = re.sub(r"^#{1,6}\s+.*$", "", content, flags=re.MULTILINE)

    # Remove instruction/metadata lines
    content = re.sub(
        r"^.*(?:Pending_Approval|Approved|Rejected|Move this|approval|APPROVE|EDIT|REJECT|Instructions|Drafted by).*$",
        "", content, flags=re.MULTILINE | re.IGNORECASE
    )

    # Clean up extra blank lines
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    return content


# ── Facebook Poster ─────────────────────────────────────────────────────────────

class FacebookPoster:
    """Posts content to a Facebook Page using Playwright browser automation."""

    def __init__(self):
        SESSION_PATH.mkdir(parents=True, exist_ok=True)

    def _log(self, action: str, details: str):
        today = datetime.now().strftime("%Y-%m-%d")
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        entry = f"[{datetime.now(timezone.utc).isoformat()}] [Facebook] {action}: {details}\n"
        with open(LOGS_DIR / f"{today}.log", "a", encoding="utf-8") as f:
            f.write(entry)

    def setup_session(self):
        """Open browser, let user login manually, save session. Run once."""
        if not PLAYWRIGHT_AVAILABLE:
            print("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return False

        session_file = SESSION_PATH / "state.json"
        print("\n" + "="*50)
        print("FACEBOOK SESSION SETUP")
        print("="*50)
        print("Browser khulega — Facebook pe manually login karo.")
        print("Login ke baad terminal pe Enter dabaо — session save ho jayegi.")
        print("="*50 + "\n")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=(sys.platform != "win32"),
                args=["--start-maximized", "--no-sandbox"],
            )
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page    = context.new_page()

            page.goto("https://www.facebook.com/login", wait_until="commit", timeout=60000)
            print("Browser mein Facebook login karo... (2FA bhi complete karo agar aaye)")
            input("\nLogin complete hone ke baad yahan Enter dabaо: ")

            context.storage_state(path=str(session_file))
            browser.close()

        print(f"\nSession saved: {session_file}")
        print("Ab normal posting kaam karegi!\n")
        return True

    def post(self, content: str) -> dict:
        """Open Facebook Page and create a post with the given content."""
        if not PLAYWRIGHT_AVAILABLE:
            return {
                "status": "error",
                "message": "Playwright not installed. Run: pip install playwright && playwright install chromium",
            }

        if DRY_RUN:
            logger.info(f"[DRY RUN] Would post to Facebook:\n{content[:100]}...")
            self._log("POST_DRY_RUN", content[:80])
            return {"status": "dry_run", "message": "DRY RUN — post not sent"}

        if not FACEBOOK_PAGE_URL:
            return {"status": "error", "message": "FACEBOOK_PAGE_URL not set in .env"}

        session_file = SESSION_PATH / "state.json"

        if not session_file.exists():
            return {
                "status": "error",
                "message": "No saved session. Run: python watchers/facebook_watcher.py --setup",
            }

        try:
            with sync_playwright() as p:
                logger.info("Launching browser (headless)...")
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                context = browser.new_context(
                    storage_state=str(session_file),
                    viewport={"width": 1280, "height": 800},
                )
                page = context.new_page()

                # ── Login check ────────────────────────────────────────────────
                logger.info("Opening Facebook...")
                page.goto("https://www.facebook.com/", wait_until="commit", timeout=60000)
                time.sleep(4)

                # Session expired?
                if "login" in page.url or page.query_selector("input[name='email']"):
                    browser.close()
                    return {
                        "status": "error",
                        "message": "Session expired. Run: python watchers/facebook_watcher.py --setup",
                    }

                logger.info("Logged in via saved session.")

                # ── Go to Facebook Page ────────────────────────────────────────
                logger.info(f"Navigating to Page: {FACEBOOK_PAGE_URL}")
                page.goto(FACEBOOK_PAGE_URL, wait_until="commit", timeout=60000)
                time.sleep(4)

                # Screenshot 1 — page load
                debug_dir = Path("debug_screenshots")
                debug_dir.mkdir(exist_ok=True)
                page.screenshot(path=str(debug_dir / "fb_1_page_loaded.png"))
                logger.info(f"Screenshot saved: debug_screenshots/fb_1_page_loaded.png")

                # ── Switch into Page if needed ─────────────────────────────────
                try:
                    switch_btn = page.get_by_role("button", name="Switch Now")
                    if switch_btn.is_visible(timeout=4000):
                        logger.info("Switching into Page...")
                        switch_btn.click()
                        # Wait for Facebook to process the switch — DON'T navigate manually
                        time.sleep(5)
                        logger.info("Switched into Page — now at: " + page.url)
                        page.screenshot(path=str(debug_dir / "fb_1b_switched.png"))
                        logger.info("Screenshot saved: debug_screenshots/fb_1b_switched.png")
                except Exception:
                    pass  # Already in Page context

                # ── Dismiss setup/onboarding cards ────────────────────────────
                page.keyboard.press("Escape")
                time.sleep(1)
                # Close "Finish setting up your Page" card
                for close_sel in [
                    "div[aria-label='Close']",
                    "div[aria-label='Dismiss']",
                    "div[role='button'][aria-label='Close']",
                ]:
                    try:
                        btns = page.query_selector_all(close_sel)
                        for btn in btns:
                            if btn.is_visible():
                                btn.click()
                                time.sleep(1)
                                break
                    except Exception:
                        continue

                # ── Navigate to Meta Business Suite composer ───────────────────
                logger.info("Navigating to Meta Business Suite post composer...")
                page.goto(
                    "https://business.facebook.com/latest/composer/",
                    wait_until="commit", timeout=60000
                )
                time.sleep(5)
                page.screenshot(path=str(debug_dir / "fb_composer_page.png"))
                logger.info("Screenshot: debug_screenshots/fb_composer_page.png")

                # ── Dismiss any popups / tooltips ──────────────────────────────
                logger.info("Dismissing any popups...")
                for dismiss_sel in [
                    "div[aria-label='Close']",
                    "div[aria-label='Dismiss']",
                    "button[aria-label='Close']",
                ]:
                    try:
                        btns = page.query_selector_all(dismiss_sel)
                        for btn in btns:
                            if btn.is_visible():
                                btn.click()
                                time.sleep(1)
                    except Exception:
                        pass

                # Dismiss "Got it" / "OK" tooltips by text
                for got_it_text in ["Got it", "OK", "Dismiss", "Not now"]:
                    try:
                        btn = page.get_by_role("button", name=got_it_text)
                        if btn.is_visible(timeout=2000):
                            btn.click()
                            time.sleep(1)
                            logger.info(f"Dismissed popup: '{got_it_text}'")
                    except Exception:
                        pass

                time.sleep(2)
                page.screenshot(path=str(debug_dir / "fb_2_after_dismiss.png"))
                logger.info("Screenshot: debug_screenshots/fb_2_after_dismiss.png")

                # ── Find text area in composer ─────────────────────────────────
                # Meta Business Suite composer has a textarea under "Text" label
                logger.info("Finding post text area...")
                editor = None

                editor_selectors = [
                    "textarea[placeholder]",                          # plain textarea
                    "textarea",                                       # any textarea
                    "div[contenteditable='true'][spellcheck='true']", # rich text
                    "div[data-lexical-editor='true']",                # Lexical editor
                    "div[role='textbox'][contenteditable='true']",    # ARIA textbox
                    "div[contenteditable='true']",                    # any contenteditable
                    "div[role='textbox']",                            # role textbox
                ]

                for ed_sel in editor_selectors:
                    try:
                        editor = page.wait_for_selector(ed_sel, timeout=5000)
                        if editor and editor.is_visible():
                            logger.info(f"Found editor: {ed_sel}")
                            break
                        editor = None
                    except Exception:
                        continue

                if not editor:
                    page.screenshot(path=str(debug_dir / "fb_error_no_editor.png"))
                    raise RuntimeError(
                        "Could not find the post text editor. "
                        "Check debug_screenshots/fb_composer_page.png"
                    )

                # Screenshot 3 — before typing
                page.screenshot(path=str(debug_dir / "fb_3_modal.png"))
                logger.info("Screenshot: debug_screenshots/fb_3_modal.png")

                # ── Type post content ──────────────────────────────────────────
                editor.click()
                time.sleep(1)
                page.keyboard.type(content, delay=30)
                time.sleep(2)

                # Screenshot 4 — after typing, before submit
                page.screenshot(path=str(debug_dir / "fb_4_before_post_btn.png"))
                logger.info("Screenshot: debug_screenshots/fb_4_before_post_btn.png")

                # ── Click Publish / Post button ────────────────────────────────
                posted = False

                # "Publish" is the button in Meta Business Suite
                for btn_name in ["Publish", "Post", "Share"]:
                    try:
                        btn = page.get_by_role("button", name=btn_name)
                        if btn.is_visible(timeout=3000) and btn.is_enabled():
                            btn.click()
                            posted = True
                            logger.info(f"Clicked: '{btn_name}'")
                            break
                    except Exception:
                        continue

                # CSS fallback
                if not posted:
                    for sel in [
                        "button:has-text('Publish')",
                        "button:has-text('Post')",
                        "div[aria-label='Publish'][role='button']",
                        "div[aria-label='Post'][role='button']",
                    ]:
                        try:
                            el = page.wait_for_selector(sel, timeout=3000)
                            if el and el.is_visible() and el.is_enabled():
                                el.click()
                                posted = True
                                logger.info(f"Clicked (CSS): {sel}")
                                break
                        except Exception:
                            continue

                if not posted:
                    page.screenshot(path=str(debug_dir / "fb_error_no_post_btn.png"))
                    raise RuntimeError("Could not find the Publish button.")

                time.sleep(4)
                logger.info("Facebook post published!")
                self._log("POST_SUCCESS", f"chars={len(content)}")
                browser.close()
                return {"status": "success", "message": "Post published on Facebook"}

        except Exception as e:
            logger.error(f"Facebook post failed: {e}")
            self._log("POST_ERROR", str(e)[:200])
            return {"status": "error", "message": str(e)[:200]}



# ── Watcher ─────────────────────────────────────────────────────────────────────

class FacebookWatcher(BaseWatcher):
    """Watches /Approved/ for FACEBOOK_*.md files and posts them."""

    def __init__(self, vault_path: str, check_interval: int = 30):
        super().__init__(vault_path, check_interval=check_interval)
        self.approved_dir = VAULT_PATH / "Approved"
        self.done_dir     = VAULT_PATH / "Done"
        self.poster       = FacebookPoster()
        self._posted: set = set()

    def check_for_updates(self) -> list:
        return [
            f for f in self.approved_dir.glob("FACEBOOK_*.md")
            if str(f) not in self._posted
        ]

    def create_action_file(self, item: Path) -> Path:
        content = extract_post_content(item)

        if not content.strip():
            logger.warning(f"Empty content in {item.name} — skipping")
            self._posted.add(str(item))
            return item

        logger.info(f"Posting: {item.name}")
        logger.info(f"Preview: {content[:80]}...")

        result = self.poster.post(content)

        if result["status"] in ("success", "dry_run"):
            raw = item.read_text(encoding="utf-8")
            raw = raw.replace("status: pending_approval", "status: posted")
            raw += f"\n\n## Posted [{datetime.now(timezone.utc).isoformat()}]\n- **Result:** {result['message']}\n"

            done_path = self.done_dir / item.name
            done_path.write_text(raw, encoding="utf-8")
            item.unlink()

            logger.info(f"Moved to Done: {item.name}")
            self.log_event("FACEBOOK_POSTED", item.name)
            self._update_dashboard(item.name, result["status"])
        else:
            logger.error(f"Post failed: {result['message']}")
            self.log_event("FACEBOOK_ERROR", result["message"])

        self._posted.add(str(item))
        return item

    def _update_dashboard(self, filename: str, status: str):
        dashboard = VAULT_PATH / "Dashboard.md"
        if not dashboard.exists():
            return
        dash = dashboard.read_text(encoding="utf-8")
        row = f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Facebook post {status}: {filename} |"
        dash = dash.replace(
            "| Time (UTC)          | Action                                      |",
            "| Time (UTC)          | Action                                      |\n" + row
        )
        dashboard.write_text(dash, encoding="utf-8")


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AI Employee — Facebook Watcher")
    parser.add_argument("--vault",      default=os.getenv("VAULT_PATH", "AI_Employee_Vault"))
    parser.add_argument("--interval",   type=int, default=30)
    parser.add_argument("--post-now",   action="store_true")
    parser.add_argument("--dry-run",    action="store_true")
    parser.add_argument("--setup",      action="store_true", help="Save login session (run once)")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
        global DRY_RUN
        DRY_RUN = True

    if args.setup:
        FacebookPoster().setup_session()
        return

    watcher = FacebookWatcher(vault_path=args.vault, check_interval=args.interval)

    if args.post_now:
        items = watcher.check_for_updates()
        logger.info(f"Found {len(items)} approved post(s)")
        for item in items:
            watcher.create_action_file(item)
        logger.info("Done.")
    else:
        watcher.run()


if __name__ == "__main__":
    main()
