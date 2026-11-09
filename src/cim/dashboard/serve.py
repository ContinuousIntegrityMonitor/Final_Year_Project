"""Serve the status board on localhost. The page polls /api/board."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from cim.dashboard.board import as_dict, load_board
from cim.dashboard.page import render_page
from cim.mcp.envelope import WARMUP


def make_server(db: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Bind a server that answers the page and the live JSON feed."""
    store = db

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                body = render_page(load_board(store)).encode("utf-8")
                content_type = "text/html; charset=utf-8"
            elif path == "/api/board":
                payload = as_dict(load_board(store))
                payload["warmup"] = WARMUP
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

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)
