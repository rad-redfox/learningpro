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
import urllib.request
import urllib.error

PORT = int(os.environ.get("PORT", "8888"))
MODEL = "claude-sonnet-4-6"     # forced server-side, same as the Netlify function
MAX_TOKENS_CAP = 4096

os.chdir(os.path.dirname(os.path.abspath(__file__)))


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path.split("?")[0] != "/api/claude":
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

    def _json(self, status, obj):
        b = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer(("", PORT), Handler) as httpd:
        print(f"Learning Pro dev server → http://localhost:{PORT}")
        if os.environ.get("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY detected — AI tutor and Life games will work.")
        else:
            print("⚠️  ANTHROPIC_API_KEY not set — AI features will return a 'not configured' message.")
        print("Press Ctrl+C to stop.")
        httpd.serve_forever()
