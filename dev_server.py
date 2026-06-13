#!/usr/bin/env python3
"""
Local dev server for Learning Pro.

Serves the static site AND runs the /api/claude proxy locally — so you can test
the AI tutor and Life games on your own machine without Netlify or Node.js.
(A plain `python3 -m http.server` can't do this: it returns 501 to the POST
requests the AI features make, because it only implements GET/HEAD.)

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...     # your key from console.anthropic.com
    python3 dev_server.py                    # then open http://localhost:8888

In production, Netlify serves the static files and runs netlify/functions/claude.js.
This script just mirrors that function for local testing; it is not deployed.
"""

import http.server
import socketserver
import json
import os
import time
import hmac
import hashlib
import base64
import urllib.request
import urllib.parse
import urllib.error

PORT = int(os.environ.get("PORT", "8888"))
MODEL = "claude-sonnet-4-6"     # forced server-side, same as the Netlify function
MAX_TOKENS_CAP = 4096
PASS_DAYS = 60                  # mirrors netlify/functions/pass.js

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def _b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _pass_sign(payload, secret):
    body = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64url(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return body + "." + sig


def _pass_verify(token, secret):
    try:
        body, sig = str(token).split(".")
        expect = _b64url(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            return None
        pad = "=" * (-len(body) % 4)
        return json.loads(base64.urlsafe_b64decode(body + pad).decode())
    except Exception:
        return None


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/pass":
            return self._handle_pass()
        if path != "/api/claude":
            return self._json(404, {"error": "Not found"})

        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            return self._json(500, {
                "error": "Server not configured: set ANTHROPIC_API_KEY before running dev_server.py."
            })

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            return self._json(400, {"error": "Invalid JSON body"})

        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            return self._json(400, {"error": "messages must be a non-empty array"})

        try:
            max_tokens = max(1, min(int(body.get("max_tokens") or 1024), MAX_TOKENS_CAP))
        except Exception:
            max_tokens = 1024

        payload = json.dumps({
            "model": MODEL,
            "max_tokens": max_tokens,
            "messages": messages,
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data, status = resp.read(), resp.status
        except urllib.error.HTTPError as e:
            data, status = e.read(), e.code  # pass Anthropic's error body through
        except Exception as e:
            return self._json(502, {"error": "Upstream request failed", "detail": str(e)})

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_pass(self):
        secret = os.environ.get("PASS_SECRET")
        if not secret:
            return self._json(500, {"error": "Server not configured: set PASS_SECRET before running dev_server.py."})
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            return self._json(400, {"error": "Invalid JSON body"})
        action = body.get("action")
        if action == "verify":
            payload = _pass_verify(body.get("token"), secret)
            active = bool(payload and payload.get("exp") and payload["exp"] > time.time())
            return self._json(200, {"active": active, "exp": payload.get("exp") if payload else None})
        if action == "redeem":
            raw = str(body.get("code") or "").strip()
            if not raw:
                return self._json(400, {"ok": False, "error": "Please enter a code."})
            exp = int(time.time()) + PASS_DAYS * 24 * 60 * 60
            # 1) Manual code list
            manual = [c.strip().upper() for c in (os.environ.get("VALID_CODES") or "").split(",") if c.strip()]
            if raw.upper() in manual:
                return self._json(200, {"ok": True, "token": _pass_sign({"exp": exp}, secret), "exp": exp})
            # 2) Lemon Squeezy license key
            d = {}
            try:
                req = urllib.request.Request(
                    "https://api.lemonsqueezy.com/v1/licenses/validate",
                    data=urllib.parse.urlencode({"license_key": raw}).encode(),
                    method="POST",
                    headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
                )
                with urllib.request.urlopen(req) as resp:
                    d = json.loads(resp.read() or b"{}")
            except urllib.error.HTTPError as e:
                try: d = json.loads(e.read() or b"{}")
                except Exception: d = {}
            except Exception:
                d = {}
            want_store = os.environ.get("LEMONSQUEEZY_STORE_ID")
            store_ok = (not want_store) or (str((d.get("meta") or {}).get("store_id")) == str(want_store))
            if d.get("valid") and store_ok:
                return self._json(200, {"ok": True, "token": _pass_sign({"exp": exp}, secret), "exp": exp})
            return self._json(200, {"ok": False, "error": "That code isn’t valid. Check it and try again."})
        return self._json(400, {"error": "Unknown action"})

    def _json(self, status, obj):
        b = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


if __name__ == "__main__":
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", PORT), Handler) as httpd:
        print(f"Learning Pro dev server → http://localhost:{PORT}")
        if os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY detected — AI tutor and Life games will work.")
        else:
            print("⚠️  ANTHROPIC_API_KEY not set — AI features will return a 'not configured' message.")
        print("Press Ctrl+C to stop.")
        httpd.serve_forever()
