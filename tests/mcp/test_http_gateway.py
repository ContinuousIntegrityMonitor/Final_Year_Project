"""HTTP / Streamable-HTTP MCP gateway (T-16b)."""

from __future__ import annotations

import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from cim.common.store import BaselineStore
from cim.mcp.http_gateway import (
    GatewayConfig,
    GatewayRoute,
    join_upstream,
    load_gateway_config,
    parse_jsonrpc_bodies,
    serve_gateway,
)


def _records(db: Path) -> list[tuple[str, dict[str, Any]]]:
    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT kind, payload FROM record ORDER BY id").fetchall()
    finally:
        con.close()
    return [(str(kind), json.loads(payload)) for kind, payload in rows]


class _FakeMcp(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    seen_auth: list[str | None] = []

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        type(self).seen_auth.append(self.headers.get("Authorization"))
        body = json.loads(raw.decode())
        method = body.get("method")
        message_id = body.get("id")
        if method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Echo",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                        },
                    }
                ]
            }
            payload = json.dumps({"jsonrpc": "2.0", "id": message_id, "result": result}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if method == "tools/call":
            text = (body.get("params") or {}).get("arguments", {}).get("text", "")
            # SSE-shaped response (Streamable HTTP may use event stream).
            data = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": message_id,
                    "result": {"content": [{"type": "text", "text": text}]},
                }
            )
            payload = f"event: message\ndata: {data}\n\n".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": message_id, "result": {"protocolVersion": "2024-11-05"}}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start_fake() -> tuple[ThreadingHTTPServer, str]:
    _FakeMcp.seen_auth = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeMcp)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}/mcp"


def test_join_and_parse_helpers() -> None:
    assert join_upstream("http://x/mcp", "") == "http://x/mcp"
    assert join_upstream("http://x/mcp", "extra") == "http://x/mcp/extra"
    assert parse_jsonrpc_bodies(b'{"jsonrpc":"2.0","id":1}', "application/json")[0]["id"] == 1
    sse = b'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{}}\n\n'
    assert parse_jsonrpc_bodies(sse, "text/event-stream")[0]["id"] == 2


def test_load_gateway_config(tmp_path: Path) -> None:
    path = tmp_path / "gw.json"
    path.write_text(
        json.dumps(
            {
                "db": "logs/x.sqlite",
                "port": 9,
                "routes": [{"id": "demo", "upstream": "http://127.0.0.1:1/mcp"}],
            }
        ),
        encoding="utf-8",
    )
    cfg = load_gateway_config(path, db=tmp_path / "out.sqlite", port=55)
    assert cfg.port == 55
    assert cfg.db == tmp_path / "out.sqlite"
    assert cfg.routes[0].id == "demo"


def test_gateway_records_list_and_call(tmp_path: Path) -> None:
    upstream, upstream_url = _start_fake()
    db = tmp_path / "store.sqlite"
    try:
        config = GatewayConfig(
            db=db,
            host="127.0.0.1",
            port=0,
            routes=(
                GatewayRoute(
                    id="demo",
                    upstream=upstream_url,
                    origin="test",
                    root="test-demo",
                    authorization_env="CIM_TEST_TOKEN",
                ),
            ),
        )
        gateway = serve_gateway(config, env={"CIM_TEST_TOKEN": "secret-token"})
        gw_thread = threading.Thread(target=gateway.serve_forever, daemon=True)
        gw_thread.start()
        try:
            base = f"http://127.0.0.1:{gateway.server_address[1]}/s/demo"
            list_body = json.dumps(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            ).encode()
            call_body = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "echo", "arguments": {"text": "hi"}},
                }
            ).encode()
            with urlopen(Request(base, data=list_body, method="POST"), timeout=5) as resp:
                listed = json.loads(resp.read().decode())
            with urlopen(Request(base, data=call_body, method="POST"), timeout=5) as resp:
                assert "text/event-stream" in resp.headers.get("Content-Type", "")
                raw = resp.read()
            assert listed["result"]["tools"][0]["name"] == "echo"
            assert b'"hi"' in raw
            # Allow store writer to flush.
            import time

            time.sleep(0.3)
            records = _records(db)
            kinds = [k for k, _ in records]
            assert "artefact" in kinds
            behaviour = [p for k, p in records if k == "behaviour"]
            assert len(behaviour) == 1
            assert behaviour[0]["tool_id"] == "echo"
            assert behaviour[0]["outcome"] == "ok"
            assert "secret-token" not in json.dumps(records)
            assert _FakeMcp.seen_auth[-1] == "Bearer secret-token"
            with BaselineStore(db) as store:
                assert store.verify_chain().ok
        finally:
            gateway.shutdown()
            writer = getattr(gateway, "cim_writer", None)
            if writer is not None:
                writer.stop()
            gateway.server_close()
    finally:
        upstream.shutdown()
        upstream.server_close()
