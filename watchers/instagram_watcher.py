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
    """Extract only the caption text under '## Post Content' section."""
    raw = filepath.read_text(encoding="utf-8")

    match = re.search(
        r"##\s+Post Content\s*\n(.*?)(?:\n---|\Z)",
        raw,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if match:
        content = match.group(1).strip()
    else:
        # Fallback: strip frontmatter + headings + blockquotes + hr lines
        content = re.sub(r"^---.*?---\s*", "", raw, flags=re.DOTALL)
        content = re.sub(r"^#{1,6}\s+.*$", "", content, flags=re.MULTILINE)
        content = re.sub(r"^>.*$", "", content, flags=re.MULTILINE)
        content = re.sub(r"^-{3,}$", "", content, flags=re.MULTILINE)
        content = re.sub(
            r"^.*(?:Pending_Approval|Approved|Rejected|Move this|approval|APPROVE|EDIT|REJECT|Instructions|Drafted by|Char count|Topic:).*$",
            "", content, flags=re.MULTILINE | re.IGNORECASE,
        )
        content = re.sub(r"\n{3,}", "\n\n", content).strip()

    if len(content) > 2200:
        content = content[:2197] + "..."
    return content


def _make_caption_image(caption: str) -> Path:
    """Create a simple branded image with caption text for Instagram upload."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1080, 1080), color=(15, 15, 15))
        draw = ImageDraw.Draw(img)
        # Draw white text centered
        try:
            font = ImageFont.truetype("arial.ttf", 40)
        except Exception:
            font = ImageFont.load_default()
        # Word-wrap text
        words = caption.split()
        lines, line = [], ""
        for word in words:
            test = (line + " " + word).strip()
            if draw.textlength(test, font=font) < 900:
                line = test
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        total_h = len(lines) * 55
        y = (1080 - total_h) // 2
        for ln in lines:
            w = draw.textlength(ln, font=font)
            draw.text(((1080 - w) / 2, y), ln, fill=(255, 255, 255), font=font)
            y += 55
        img_path = Path("debug_screenshots") / "ig_post_image.png"
        img_path.parent.mkdir(exist_ok=True)
        img.save(str(img_path))
        logger.info(f"Caption image created: {img_path}")
        return img_path.resolve()
    except ImportError:
        logger.warning("Pillow not installed — using fallback blank image")
        img_path = Path("debug_screenshots") / "ig_post_image.png"
        img_path.parent.mkdir(exist_ok=True)
        # 1x1 white pixel PNG
        img_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x04\x38\x00\x00\x04\x38"
            b"\x08\x02\x00\x00\x00\xf8\x1f\x96\xfd\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
            b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        return img_path.resolve()


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
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--no-sandbox",
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="Asia/Karachi",
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            page = context.new_page()
            page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            print("Instagram login karo... (2FA bhi complete karo agar aaye)")
            print("NOTE: Home feed dikhne ke baad hi Enter dabao!")
            input("\nLogin COMPLETE hone ke baad yahan Enter dabao: ")
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

        # Instagram needs an image — generate one with the caption text
        img_path = _make_caption_image(content)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=False,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--start-maximized",
                    ],
                )
                context = browser.new_context(
                    storage_state=str(session_file),
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    timezone_id="Asia/Karachi",
                )
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
                page = context.new_page()

                logger.info("Opening Instagram...")
                page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)

                # Wait for home feed to load
                try:
                    page.wait_for_selector("svg[aria-label='New post']", timeout=20000)
                except Exception:
                    pass
                time.sleep(3)

                # Check if logged in — look for home feed nav element
                is_logged_out = "login" in page.url or "accounts" in page.url
                if not is_logged_out:
                    try:
                        page.wait_for_selector("svg[aria-label='New post']", timeout=5000)
                    except Exception:
                        is_logged_out = True  # nav not found = probably login page
                if is_logged_out:
                    browser.close()
                    return {"status": "error", "message": "Session expired. Run: python watchers/instagram_watcher.py --setup"}

                page.screenshot(path=str(debug_dir / "ig_1_home.png"))

                # Dismiss popups (notifications, cookies)
                for dismiss_text in ["Not Now", "Cancel", "Allow", "Block"]:
                    try:
                        btn = page.get_by_role("button", name=dismiss_text)
                        if btn.is_visible(timeout=1500):
                            btn.click()
                            time.sleep(1)
                    except Exception:
                        pass

                # Click "New Post" (+ icon in nav)
                logger.info("Opening new post composer...")
                clicked = False
                for sel in [
                    "svg[aria-label='New post']",
                    "[aria-label='New post']",
                    "a[href='/create/select/']",
                ]:
                    try:
                        el = page.wait_for_selector(sel, timeout=5000)
                        if el and el.is_visible():
                            el.click()
                            clicked = True
                            logger.info(f"Clicked new post: {sel}")
                            time.sleep(2)
                            break
                    except Exception:
                        continue

                page.screenshot(path=str(debug_dir / "ig_2_create.png"))

                # Upload the image via file input
                logger.info(f"Uploading image: {img_path}")
                try:
                    # Set file on the hidden file input
                    with page.expect_file_chooser() as fc_info:
                        # Try clicking "Select from computer" button
                        for sel in [
                            "button:has-text('Select from computer')",
                            "button:has-text('Select from')",
                            "input[type='file']",
                        ]:
                            try:
                                el = page.wait_for_selector(sel, timeout=5000)
                                if el:
                                    el.click()
                                    break
                            except Exception:
                                continue
                    fc_info.value.set_files(str(img_path))
                    logger.info("Image uploaded via file chooser.")
                except Exception:
                    # Fallback: set file directly on input
                    try:
                        file_input = page.wait_for_selector("input[type='file']", timeout=5000)
                        if file_input:
                            file_input.set_input_files(str(img_path))
                            logger.info("Image set via input[type=file].")
                    except Exception as fe:
                        logger.warning(f"File upload fallback failed: {fe}")

                time.sleep(3)
                page.screenshot(path=str(debug_dir / "ig_3_uploaded.png"))

                # Click through crop / filter / Next screens
                for _ in range(3):
                    for btn_name in ["Next", "Crop", "OK"]:
                        try:
                            btn = page.get_by_role("button", name=btn_name)
                            if btn.is_visible(timeout=2000) and btn.is_enabled():
                                btn.click()
                                logger.info(f"Clicked: '{btn_name}'")
                                time.sleep(2)
                                break
                        except Exception:
                            pass

                page.screenshot(path=str(debug_dir / "ig_4_caption.png"))

                # Type caption
                caption_typed = False
                for sel in [
                    "div[aria-label='Write a caption...']",
                    "textarea[aria-label='Write a caption...']",
                    "textarea[placeholder*='caption']",
                    "div[contenteditable='true']",
                    "textarea",
                ]:
                    try:
                        el = page.wait_for_selector(sel, timeout=5000)
                        if el and el.is_visible():
                            el.click()
                            time.sleep(1)
                            page.keyboard.type(content, delay=15)
                            caption_typed = True
                            logger.info(f"Caption typed: {sel}")
                            break
                    except Exception:
                        continue

                if not caption_typed:
                    page.screenshot(path=str(debug_dir / "ig_error_no_caption.png"))
                    raise RuntimeError("Could not find caption input. Check ig_4_caption.png")

                time.sleep(2)
                page.screenshot(path=str(debug_dir / "ig_5_typed.png"))

                # Click Share — it's a link not a button on Instagram web
                posted = False
                # Try link first (Instagram uses <a> for Share)
                for sel in [
                    "a:has-text('Share')",
                    "[role='link']:has-text('Share')",
                ]:
                    try:
                        el = page.wait_for_selector(sel, timeout=3000)
                        if el and el.is_visible():
                            el.click()
                            posted = True
                            logger.info(f"Clicked Share link: {sel}")
                            break
                    except Exception:
                        continue

                # Fallback: button
                if not posted:
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
                    raise RuntimeError("Could not find Share button. Check ig_5_typed.png")

                # Wait for post confirmation screen
                time.sleep(8)
                page.screenshot(path=str(debug_dir / "ig_6_after_share.png"))
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
