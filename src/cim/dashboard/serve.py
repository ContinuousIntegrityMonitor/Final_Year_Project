"""Serve the status board on localhost. The page polls /api/board.

Write endpoints (`POST /api/call`) are off unless ``demo=True``. Demo mode also
requires a per-run token and rejects unexpected Host/Origin (X1).
"""

from __future__ import annotations

import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, urlsplit

from cim.dashboard.board import as_dict, load_board
from cim.dashboard.call_demo import (
    clear_demo,
    read_connected,
    run_demo_call,
    tamper_log,
)
from cim.dashboard.page import render_page
from cim.mcp.envelope import WARMUP


def make_server(
    db: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    demo: bool = False,
    demo_token: str | None = None,
) -> ThreadingHTTPServer:
    """Bind a server that answers the page and the live JSON feed.

    When ``demo`` is False the board is read-only: ``POST /api/call`` returns 404.
    When ``demo`` is True a token is required on every write (header
    ``X-CIM-Demo-Token``, or query/body ``token``).
    """
    store = db
    token = (demo_token or "").strip() if demo else ""
    if demo and not token:
        token = secrets.token_urlsafe(18)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            connected = read_connected(store)
            if path in {"/", "/index.html"}:
                body = render_page(
                    load_board(store),
                    connected=connected,
                    demo=demo,
                    demo_token=token if demo else "",
                ).encode("utf-8")
                content_type = "text/html; charset=utf-8"
            elif path == "/api/board":
                payload = as_dict(load_board(store))
                payload["warmup"] = WARMUP
                payload["connected"] = connected
                payload["demo"] = demo
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
            if not demo:
                self.send_error(404, "demo actions disabled; pass --demo")
                return
            refused = _client_allowed(self.headers, listen_host=host, token=token)
            if refused is not None:
                self.send_error(401, refused)
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

    server = ThreadingHTTPServer((host, port), Handler)
    server.cim_demo_token = token  # type: ignore[attr-defined]
    return server


def _header(headers: object, name: str) -> str:
    items = getattr(headers, "items", None)
    if items is None:
        return ""
    want = name.lower()
    for key, value in items():
        if str(key).lower() == want:
            return str(value)
    return ""


def _client_allowed(headers: object, *, listen_host: str, token: str) -> str | None:
    """Return a refusal reason, or None when the write is allowed."""
    host = _header(headers, "Host")
    host_only = host.split(":", 1)[0].strip().lower()
    expected = {listen_host.lower(), "127.0.0.1", "localhost", "::1"}
    if host_only and host_only not in expected:
        return "invalid Host"
    origin = _header(headers, "Origin").strip()
    if origin:
        origin_host = urlsplit(origin).hostname or ""
        if origin_host.lower() not in {"127.0.0.1", "localhost", "::1"} and origin != "null":
            return "invalid Origin"
    provided = _header(headers, "X-CIM-Demo-Token").strip()
    if not provided or provided != token:
        return "missing or wrong demo token"
    return None
