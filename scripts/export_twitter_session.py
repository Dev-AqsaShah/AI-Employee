"""
export_twitter_session.py

Chrome se Twitter cookies export karke Playwright session format mein save karta hai.
Chrome BAND hona chahiye pehle!

Usage:
    python scripts/export_twitter_session.py
"""
import os
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone

CHROME_COOKIES_DB = Path(os.path.expandvars(
    r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies"
))
SESSION_OUT = Path("credentials/twitter_session/state.json")

TWITTER_DOMAINS = [".x.com", "x.com", ".twitter.com", "twitter.com"]


def export():
    if not CHROME_COOKIES_DB.exists():
        print("Chrome Cookies file nahi mila:", CHROME_COOKIES_DB)
        return False

    # Open SQLite in immutable read-only mode — works even if Chrome has it locked
    uri = CHROME_COOKIES_DB.as_uri() + "?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except Exception:
        # Fallback: copy to temp then open
        tmp = Path(tempfile.mktemp(suffix=".db"))
        shutil.copy2(CHROME_COOKIES_DB, tmp)
        conn = sqlite3.connect(str(tmp))

    cur = conn.cursor()
    cur.execute(
        "SELECT host_key, name, value, path, expires_utc, is_secure, is_httponly "
        "FROM cookies WHERE host_key LIKE '%twitter%' OR host_key LIKE '%x.com%'"
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("Chrome mein Twitter cookies nahi mile — pehle Chrome mein x.com login karo!")
        return False

    cookies = []
    for host, name, value, path, expires_utc, secure, httponly in rows:
        # Chrome stores epoch in microseconds since 1601-01-01
        if expires_utc:
            expires = (expires_utc / 1_000_000) - 11644473600
        else:
            expires = -1
        cookies.append({
            "name": name,
            "value": value,
            "domain": host,
            "path": path,
            "expires": expires,
            "httpOnly": bool(httponly),
            "secure": bool(secure),
            "sameSite": "Lax"
        })

    state = {
        "cookies": cookies,
        "origins": []
    }

    SESSION_OUT.parent.mkdir(parents=True, exist_ok=True)
    SESSION_OUT.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"\nDone! {len(cookies)} Twitter cookies export hue.")
    print(f"Session saved: {SESSION_OUT}")
    return True


if __name__ == "__main__":
    print("Chrome BAND hai? (Ctrl+C dabao agar open hai)")
    print("Extracting Twitter session from Chrome...\n")
    export()
