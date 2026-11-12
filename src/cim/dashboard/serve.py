"""Serve the status board on localhost. The page polls /api/board."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from cim.dashboard.board import as_dict, load_board
from cim.dashboard.call_demo import (
    clear_demo,
    read_connected,
    run_demo_call,
    tamper_log,
)
from cim.dashboard.page import render_page
from cim.mcp.envelope import WARMUP


def make_server(db: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Bind a server that answers the page and the live JSON feed."""
    store = db

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            connected = read_connected(store)
            if path in {"/", "/index.html"}:
                body = render_page(load_board(store), connected=connected).encode("utf-8")
                content_type = "text/html; charset=utf-8"
            elif path == "/api/board":
                payload = as_dict(load_board(store))
                payload["warmup"] = WARMUP
                payload["connected"] = connected
                body = json.dumps(payload).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path != "/api/call":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                incoming = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self.send_error(400)
                return
            action = "call"
            if isinstance(incoming, dict):
                raw_action = incoming.get("action")
                if isinstance(raw_action, str):
                    action = raw_action
                elif incoming.get("unusual") is True:
                    action = "change"
            if action == "clear":
                payload = clear_demo(store)
            elif action == "tamper":
                payload = tamper_log(store)
            else:
                unusual = action == "change"
                connect_only = action == "connect"
                payload = run_demo_call(store, unusual, connect_only=connect_only)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)
