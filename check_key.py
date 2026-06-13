#!/usr/bin/env python3
"""
Check that ANTHROPIC_API_KEY is set and valid — before you start testing.

Uses GET /v1/models, which authenticates the key but generates no message,
so it costs nothing. Exits 0 if the key works, non-zero otherwise.

Usage:
    python3 check_key.py
"""

import os
import sys
import json
import urllib.request
import urllib.error

key = os.environ.get("ANTHROPIC_API_KEY")
if not key:
    print("❌ ANTHROPIC_API_KEY is not set in this shell.")
    print("   Set it, then re-run:  export ANTHROPIC_API_KEY=sk-ant-...")
    sys.exit(1)

req = urllib.request.Request(
    "https://api.anthropic.com/v1/models",
    headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
)

try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read() or b"{}")
    models = [m.get("id") for m in data.get("data", [])]
    print(f"✅ Key is valid. {len(models)} models available.")
    if "claude-sonnet-4-6" in models:
        print("   claude-sonnet-4-6 (used by the app) is accessible.")
    else:
        print("   ⚠️  claude-sonnet-4-6 not listed — the app may need a different model.")
    sys.exit(0)
except urllib.error.HTTPError as e:
    try:
        msg = json.loads(e.read() or b"{}").get("error", {}).get("message", "")
    except Exception:
        msg = ""
    if e.code == 401:
        print("❌ Key is invalid or revoked (401). Check it at console.anthropic.com.")
    elif e.code == 403:
        print("❌ Key lacks permission (403).", msg)
    elif e.code == 429:
        print("⚠️  Rate limited (429) — the key is valid but throttled right now.")
    else:
        print(f"❌ API returned {e.code}.", msg)
    sys.exit(1)
except Exception as e:
    print(f"❌ Could not reach the API (network issue?): {e}")
    sys.exit(1)
