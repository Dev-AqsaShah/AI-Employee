"""
instagram_watcher.py — Instagram Auto-Poster for AI Employee (Gold Tier)

Uses Playwright browser automation (NO API needed).
Watches Approved/ for INSTAGRAM_*.md files and posts to Instagram.

Setup:
  1. Set in .env:
       INSTAGRAM_USERNAME=your_instagram_username
       INSTAGRAM_PASSWORD=your_instagram_password

Usage:
    python watchers/instagram_watcher.py            # Watch mode
    python watchers/instagram_watcher.py --setup    # Save login session (run once)
    python watchers/instagram_watcher.py --post-now # Post all approved immediately
    python watchers/instagram_watcher.py --dry-run  # Test without posting
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
    format="%(asctime)s [InstagramWatcher] %(levelname)s: %(message)s",
)
logger = logging.getLogger("InstagramWatcher")

# ── Config ───────────────────────────────────────────────────────────────────────
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "")
VAULT_PATH         = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault"))
SESSION_PATH       = Path(os.getenv("INSTAGRAM_SESSION_PATH", "credentials/instagram_session"))
DRY_RUN            = os.getenv("DRY_RUN", "false").lower() == "true"

APPROVED_DIR = VAULT_PATH / "Approved"
DONE_DIR     = VAULT_PATH / "Done"
LOGS_DIR     = VAULT_PATH / "Logs"


def extract_post_content(filepath: Path) -> str:
    content = filepath.read_text(encoding="utf-8")
    content = re.sub(r"^---.*?---\s*", "", content, flags=re.DOTALL)
    content = re.sub(r"^#{1,6}\s+.*$", "", content, flags=re.MULTILINE)
    content = re.sub(
        r"^.*(?:Pending_Approval|Approved|Rejected|Move this|approval|APPROVE|EDIT|REJECT|Instructions|Drafted by).*$",
        "", content, flags=re.MULTILINE | re.IGNORECASE
    )
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    # Instagram limit: 2200 chars
    if len(content) > 2200:
        content = content[:2197] + "..."
    return content


class InstagramPoster:
    def __init__(self):
        SESSION_PATH.mkdir(parents=True, exist_ok=True)

    def _log(self, action: str, details: str):
        today = datetime.now().strftime("%Y-%m-%d")
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        entry = f"[{datetime.now(timezone.utc).isoformat()}] [Instagram] {action}: {details}\n"
        with open(LOGS_DIR / f"{today}.log", "a", encoding="utf-8") as f:
            f.write(entry)

    def setup_session(self):
        """Open browser for manual Instagram login. Run once."""
        if not PLAYWRIGHT_AVAILABLE:
            print("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return False

        session_file = SESSION_PATH / "state.json"
        print("\n" + "="*50)
        print("INSTAGRAM SESSION SETUP")
        print("="*50)
        print("Browser khulega — Instagram pe manually login karo.")
        print("Login ke baad terminal pe Enter dabaو — session save ho jayegi.")
        print("="*50 + "\n")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=["--no-sandbox"])
            context = browser.new_context(viewport={"width": 375, "height": 812})
            page = context.new_page()
            page.goto("https://www.instagram.com/accounts/login/", wait_until="commit", timeout=60000)
            print("Instagram login karo... (2FA bhi complete karo agar aaye)")
            input("\nLogin complete hone ke baad yahan Enter dabaо: ")
            context.storage_state(path=str(session_file))
            browser.close()

        print(f"\nSession saved: {session_file}")
        return True

    def post(self, content: str) -> dict:
        if not PLAYWRIGHT_AVAILABLE:
            return {"status": "error", "message": "Playwright not installed"}

        if DRY_RUN:
            logger.info(f"[DRY RUN] Would post to Instagram:\n{content[:100]}...")
            self._log("POST_DRY_RUN", content[:80])
            return {"status": "dry_run", "message": "DRY RUN — post not sent"}

        session_file = SESSION_PATH / "state.json"
        if not session_file.exists():
            return {"status": "error", "message": "No saved session. Run: python watchers/instagram_watcher.py --setup"}

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
                    viewport={"width": 375, "height": 812},
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
                )
                page = context.new_page()

                logger.info("Opening Instagram...")
                page.goto("https://www.instagram.com/", wait_until="commit", timeout=60000)
                time.sleep(4)

                if "login" in page.url:
                    browser.close()
                    return {"status": "error", "message": "Session expired. Run --setup again"}

                page.screenshot(path=str(debug_dir / "ig_1_home.png"))

                # Dismiss notifications popup
                for dismiss_text in ["Not Now", "Cancel", "Block"]:
                    try:
                        btn = page.get_by_role("button", name=dismiss_text)
                        if btn.is_visible(timeout=2000):
                            btn.click()
                            time.sleep(1)
                    except Exception:
                        pass

                # Click "New Post" button (+ icon)
                logger.info("Opening new post composer...")
                clicked = False
                for sel in [
                    "[aria-label='New post']",
                    "svg[aria-label='New post']",
                    "[data-testid='new-post-button']",
                    "a[href='/create/style/']",
                ]:
                    try:
                        el = page.wait_for_selector(sel, timeout=4000)
                        if el and el.is_visible():
                            el.click()
                            clicked = True
                            logger.info(f"Clicked new post: {sel}")
                            break
                    except Exception:
                        continue

                if not clicked:
                    # Try navigating directly to create page
                    page.goto("https://www.instagram.com/create/style/", wait_until="commit", timeout=30000)
                    time.sleep(3)

                page.screenshot(path=str(debug_dir / "ig_2_create.png"))
                time.sleep(3)

                # Instagram web doesn't support text-only posts directly
                # Use mobile view approach — navigate to create post
                # For text posts, we write caption directly

                # Find caption input
                caption_sel = None
                for sel in [
                    "textarea[aria-label='Write a caption...']",
                    "textarea[placeholder*='caption']",
                    "div[aria-label='Write a caption...']",
                    "div[contenteditable='true']",
                    "textarea",
                ]:
                    try:
                        el = page.wait_for_selector(sel, timeout=5000)
                        if el and el.is_visible():
                            caption_sel = sel
                            el.click()
                            page.keyboard.type(content, delay=20)
                            logger.info(f"Typed caption: {sel}")
                            break
                    except Exception:
                        continue

                if not caption_sel:
                    page.screenshot(path=str(debug_dir / "ig_error_no_caption.png"))
                    raise RuntimeError("Could not find caption input. Check ig_2_create.png")

                time.sleep(2)
                page.screenshot(path=str(debug_dir / "ig_3_typed.png"))

                # Click Share / Post button
                posted = False
                for btn_name in ["Share", "Post", "Publish"]:
                    try:
                        btn = page.get_by_role("button", name=btn_name)
                        if btn.is_visible(timeout=3000) and btn.is_enabled():
                            btn.click()
                            posted = True
                            logger.info(f"Clicked: '{btn_name}'")
                            break
                    except Exception:
                        continue

                if not posted:
                    page.screenshot(path=str(debug_dir / "ig_error_no_share.png"))
                    raise RuntimeError("Could not find Share button")

                time.sleep(4)
                logger.info("Instagram post published!")
                self._log("POST_SUCCESS", f"chars={len(content)}")
                browser.close()
                return {"status": "success", "message": "Post published on Instagram"}

        except Exception as e:
            logger.error(f"Instagram post failed: {e}")
            self._log("POST_ERROR", str(e)[:200])
            return {"status": "error", "message": str(e)[:200]}


class InstagramWatcher(BaseWatcher):
    def __init__(self, vault_path: str, check_interval: int = 30):
        super().__init__(vault_path, check_interval=check_interval)
        self.approved_dir = VAULT_PATH / "Approved"
        self.done_dir     = VAULT_PATH / "Done"
        self.poster       = InstagramPoster()
        self._posted: set = set()

    def check_for_updates(self) -> list:
        return [
            f for f in self.approved_dir.glob("INSTAGRAM_*.md")
            if str(f) not in self._posted
        ]

    def create_action_file(self, item: Path) -> Path:
        content = extract_post_content(item)
        if not content.strip():
            logger.warning(f"Empty content in {item.name} — skipping")
            self._posted.add(str(item))
            return item

        logger.info(f"Posting: {item.name}")
        result = self.poster.post(content)

        if result["status"] in ("success", "dry_run"):
            raw = item.read_text(encoding="utf-8")
            raw = raw.replace("status: pending_approval", "status: posted")
            raw += f"\n\n## Posted [{datetime.now(timezone.utc).isoformat()}]\n- **Result:** {result['message']}\n"
            done_path = self.done_dir / item.name
            done_path.write_text(raw, encoding="utf-8")
            item.unlink()
            logger.info(f"Moved to Done: {item.name}")
            self.log_event("INSTAGRAM_POSTED", item.name)
            self._update_dashboard(item.name, result["status"])
        else:
            logger.error(f"Post failed: {result['message']}")
            self.log_event("INSTAGRAM_ERROR", result["message"])

        self._posted.add(str(item))
        return item

    def _update_dashboard(self, filename: str, status: str):
        dashboard = VAULT_PATH / "Dashboard.md"
        if not dashboard.exists():
            return
        dash = dashboard.read_text(encoding="utf-8")
        row = f"| {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Instagram post {status}: {filename} |"
        dash = dash.replace(
            "| Time (UTC)          | Action                                      |",
            "| Time (UTC)          | Action                                      |\n" + row
        )
        dashboard.write_text(dash, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="AI Employee — Instagram Watcher")
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
        InstagramPoster().setup_session()
        return

    watcher = InstagramWatcher(vault_path=args.vault, check_interval=args.interval)

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
