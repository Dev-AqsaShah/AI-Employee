"""
sync_sessions_to_ec2.py — Copy login sessions from laptop to EC2

Run once from laptop:
    python sync_sessions_to_ec2.py

This reads saved browser sessions (LinkedIn, Instagram, Facebook, Twitter)
and uploads them to the EC2 dashboard so EC2 watchers can post too.
"""

import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("Run: pip install requests")
    sys.exit(1)

EC2_URL = "http://51.20.40.140:5000"
CREDS   = Path(__file__).parent / "credentials"

platforms = ["linkedin", "instagram", "facebook", "twitter", "whatsapp"]

sessions = {}
for p in platforms:
    session_file = CREDS / f"{p}_session" / "state.json"
    if session_file.exists():
        sessions[p] = json.loads(session_file.read_text(encoding="utf-8"))
        print(f"  Found: {p}")
    else:
        print(f"  Missing: {p} (skip)")

if not sessions:
    print("No sessions found.")
    sys.exit(1)

print(f"\nUploading {len(sessions)} sessions to EC2...")
res = requests.post(f"{EC2_URL}/api/sync-sessions", json=sessions, timeout=15)
data = res.json()
print(f"Done: {data}")
