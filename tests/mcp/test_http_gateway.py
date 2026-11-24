"""HTTP / Streamable-HTTP MCP gateway (T-16b)."""

from __future__ import annotations

import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

import pytest

from cim.common.store import BaselineStore
from cim.mcp.http_gateway import (
    GatewayConfig,
    GatewayRoute,
    join_upstream,
    load_gateway_config,
    parse_jsonrpc_bodies,
    require_gateway_token,
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
    try:
        join_upstream("http://x/mcp", "../../admin/keys")
    except ValueError as exc:
        assert "refusing" in str(exc)
    else:
        raise AssertionError("expected path escape to fail")
    try:
        join_upstream("http://x/mcp", "file:/etc/hostname")
    except ValueError as exc:
        assert "refusing" in str(exc)
    else:
        raise AssertionError("expected scheme escape to fail")
    # L1: percent-encoded dots must not bypass the escape check.
    try:
        join_upstream("http://x/mcp", "%2e%2e/admin")
    except ValueError as exc:
        assert "refusing" in str(exc)
    else:
        raise AssertionError("expected encoded path escape to fail")
    try:
        join_upstream("http://x/mcp", "%2E%2E/%2e%2e/keys")
    except ValueError as exc:
        assert "refusing" in str(exc)
    else:
        raise AssertionError("expected nested encoded escape to fail")
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
            access_token="gw-secret",
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
            try:
                urlopen(
                    Request(
                        base,
                        data=list_body,
                        method="POST",
                        headers={"Origin": "http://evil.example"},
                    ),
                    timeout=5,
                )
            except HTTPError as exc:
                assert exc.code == 401
            else:
                raise AssertionError("expected Origin refusal")
            try:
                urlopen(Request(base, data=list_body, method="POST"), timeout=5)
            except HTTPError as exc:
                assert exc.code == 401
            else:
                raise AssertionError("expected missing gateway token")
            headers = {
                "Content-Type": "application/json",
                "X-CIM-Gateway-Token": "gw-secret",
            }
            with urlopen(
                Request(base, data=list_body, method="POST", headers=headers), timeout=5
            ) as resp:
                listed = json.loads(resp.read().decode())
            with urlopen(
                Request(base, data=call_body, method="POST", headers=headers), timeout=5
            ) as resp:
                assert "text/event-stream" in resp.headers.get("Content-Type", "")
                raw = resp.read()
            assert listed["result"]["tools"][0]["name"] == "echo"
            assert b'"hi"' in raw
            writer = getattr(gateway, "cim_writer", None)
            if writer is not None:
                writer.drain()
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


def test_gateway_does_not_follow_redirects(tmp_path: Path) -> None:
    """G3: a 302 must not carry Authorization to another host."""
    seen: list[str | None] = []

    class _Redirect(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length) if length else b""
            seen.append(self.headers.get("Authorization"))
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/steal")
            self.send_header("Content-Length", "0")
            self.end_headers()

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _Redirect)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    up_url = f"http://127.0.0.1:{upstream.server_address[1]}/mcp"
    db = tmp_path / "store.sqlite"
    try:
        config = GatewayConfig(
            db=db,
            host="127.0.0.1",
            port=0,
            routes=(
                GatewayRoute(
                    id="demo",
                    upstream=up_url,
                    authorization_env="CIM_TEST_TOKEN",
                ),
            ),
            access_token="gw-secret",
        )
        gateway = serve_gateway(config, env={"CIM_TEST_TOKEN": "secret-token"})
        threading.Thread(target=gateway.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{gateway.server_address[1]}/s/demo"
            body = json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            ).encode()

            class _NoFollow(HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
                    return None

            opener = build_opener(_NoFollow)
            try:
                opener.open(
                    Request(
                        base,
                        data=body,
                        method="POST",
                        headers={
                            "Content-Type": "application/json",
                            "X-CIM-Gateway-Token": "gw-secret",
                        },
                    ),
                    timeout=5,
                )
            except HTTPError as exc:
                assert exc.code == 302
                assert "127.0.0.1:9" in (exc.headers.get("Location") or "")
            else:
                raise AssertionError("expected 302 passed through")
            assert seen == ["Bearer secret-token"]
        finally:
            gateway.shutdown()
            writer = getattr(gateway, "cim_writer", None)
            if writer is not None:
                writer.stop()
            gateway.server_close()
    finally:
        upstream.shutdown()
        upstream.server_close()


def test_h1_refuses_start_when_authorization_env_without_gateway_token(tmp_path: Path) -> None:
    path = tmp_path / "gw.json"
    path.write_text(
        json.dumps(
            {
                "routes": [
                    {
                        "id": "roma",
                        "upstream": "http://127.0.0.1:1/mcp",
                        "authorization_env": "CIM_MCP_AUTH_ROMA",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="CIM_HTTP_GATEWAY_TOKEN"):
        load_gateway_config(path, db=tmp_path / "s.sqlite")


def test_h1_serve_refuses_without_token_when_bearer_route(tmp_path: Path) -> None:
    config = GatewayConfig(
        db=tmp_path / "s.sqlite",
        host="127.0.0.1",
        port=0,
        routes=(
            GatewayRoute(
                id="demo",
                upstream="http://127.0.0.1:1/mcp",
                authorization_env="CIM_TEST_TOKEN",
            ),
        ),
        access_token="",
    )
    with pytest.raises(ValueError, match="CIM_HTTP_GATEWAY_TOKEN"):
        require_gateway_token(config)
    with pytest.raises(ValueError, match="CIM_HTTP_GATEWAY_TOKEN"):
        serve_gateway(config)


def test_l1_encoded_path_escape_never_reaches_upstream(tmp_path: Path) -> None:
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
                    authorization_env="CIM_TEST_TOKEN",
                ),
            ),
            access_token="gw-secret",
        )
        gateway = serve_gateway(config, env={"CIM_TEST_TOKEN": "secret-token"})
        threading.Thread(target=gateway.serve_forever, daemon=True).start()
        try:
            before = len(_FakeMcp.seen_auth)
            try:
                urlopen(
                    Request(
                        f"http://127.0.0.1:{gateway.server_address[1]}/s/demo/%2e%2e/admin",
                        data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}',
                        method="POST",
                        headers={
                            "Content-Type": "application/json",
                            "X-CIM-Gateway-Token": "gw-secret",
                        },
                    ),
                    timeout=5,
                )
            except HTTPError as exc:
                assert exc.code == 400
            else:
                raise AssertionError("expected encoded path refusal")
            assert len(_FakeMcp.seen_auth) == before
        finally:
            gateway.shutdown()
            writer = getattr(gateway, "cim_writer", None)
            if writer is not None:
                writer.stop()
            gateway.server_close()
    finally:
        upstream.shutdown()
        upstream.server_close()


def test_m2_sse_first_event_arrives_before_stream_ends(tmp_path: Path) -> None:
    """M2: gateway must not buffer the whole SSE body before the first byte."""
    import http.client
    import time

    class _SlowSse(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length) if length else b""
            first = (
                b"event: message\ndata: "
                + json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"content": [{"type": "text", "text": "early"}]},
                    }
                ).encode()
                + b"\n\n"
            )
            second = (
                b"event: message\ndata: "
                + json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {"content": [{"type": "text", "text": "late"}]},
                    }
                ).encode()
                + b"\n\n"
            )
            # Content-Length lets the gateway read1 the first event before sleep ends.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(first) + len(second)))
            self.end_headers()
            self.wfile.write(first)
            self.wfile.flush()
            time.sleep(1.5)
            self.wfile.write(second)
            self.wfile.flush()

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _SlowSse)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    up_url = f"http://127.0.0.1:{upstream.server_address[1]}/mcp"
    db = tmp_path / "store.sqlite"
    try:
        config = GatewayConfig(
            db=db,
            host="127.0.0.1",
            port=0,
            routes=(GatewayRoute(id="demo", upstream=up_url),),
            access_token="",
        )
        gateway = serve_gateway(config)
        threading.Thread(target=gateway.serve_forever, daemon=True).start()
        try:
            port = gateway.server_address[1]
            body = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "echo", "arguments": {"text": "x"}},
                }
            ).encode()
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            started = time.monotonic()
            conn.request(
                "POST",
                "/s/demo",
                body=body,
                headers={"Content-Type": "application/json"},
            )
            resp = conn.getresponse()
            # First SSE chunk should arrive well before the upstream's 1.5s pause ends.
            first = resp.read(40)
            elapsed = time.monotonic() - started
            assert first, "expected early SSE bytes"
            assert elapsed < 1.0, f"SSE buffered too long: {elapsed:.2f}s"
            rest = resp.read()
            conn.close()
            assert b"early" in first + rest
        finally:
            gateway.shutdown()
            writer = getattr(gateway, "cim_writer", None)
            if writer is not None:
                writer.stop()
            gateway.server_close()
    finally:
        upstream.shutdown()
        upstream.server_close()


def test_m3_two_sessions_same_request_id_both_recorded(tmp_path: Path) -> None:
    """M3: two clients reusing JSON-RPC id 7 must both leave a behaviour record."""
    upstream, upstream_url = _start_fake()
    db = tmp_path / "store.sqlite"
    try:
        config = GatewayConfig(
            db=db,
            host="127.0.0.1",
            port=0,
            routes=(GatewayRoute(id="demo", upstream=upstream_url),),
            access_token="",
        )
        gateway = serve_gateway(config)
        threading.Thread(target=gateway.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{gateway.server_address[1]}/s/demo"
            errors: list[BaseException] = []

            def _one(session_name: str, text: str) -> None:
                try:
                    call_body = json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 7,
                            "method": "tools/call",
                            "params": {"name": "echo", "arguments": {"text": text}},
                        }
                    ).encode()
                    with urlopen(
                        Request(
                            base,
                            data=call_body,
                            method="POST",
                            headers={
                                "Content-Type": "application/json",
                                "Mcp-Session-Id": session_name,
                            },
                        ),
                        timeout=5,
                    ) as resp:
                        assert resp.status == 200
                except BaseException as exc:  # noqa: BLE001 — collect for the main thread
                    errors.append(exc)

            t1 = threading.Thread(target=_one, args=("sess-a", "alpha"))
            t2 = threading.Thread(target=_one, args=("sess-b", "beta"))
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)
            assert errors == []
            writer = getattr(gateway, "cim_writer", None)
            if writer is not None:
                writer.drain()
            behaviour = [p for k, p in _records(db) if k == "behaviour"]
            assert len(behaviour) == 2
            tools = {row["tool_id"] for row in behaviour}
            assert tools == {"echo"}
        finally:
            gateway.shutdown()
            writer = getattr(gateway, "cim_writer", None)
            if writer is not None:
                writer.stop()
            gateway.server_close()
    finally:
        upstream.shutdown()
        upstream.server_close()


def test_h1_origin_null_and_non_json_post_are_refused(tmp_path: Path) -> None:
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
                    authorization_env="CIM_TEST_TOKEN",
                ),
            ),
            access_token="gw-secret",
        )
        gateway = serve_gateway(config, env={"CIM_TEST_TOKEN": "secret-token"})
        threading.Thread(target=gateway.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{gateway.server_address[1]}/s/demo"
            body = json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            ).encode()
            before = len(_FakeMcp.seen_auth)
            try:
                urlopen(
                    Request(
                        base,
                        data=body,
                        method="POST",
                        headers={
                            "Content-Type": "application/json",
                            "X-CIM-Gateway-Token": "gw-secret",
                            "Origin": "null",
                        },
                    ),
                    timeout=5,
                )
            except HTTPError as exc:
                assert exc.code == 401
            else:
                raise AssertionError("expected Origin null refusal")
            try:
                urlopen(
                    Request(
                        base,
                        data=body,
                        method="POST",
                        headers={
                            "Content-Type": "text/plain",
                            "X-CIM-Gateway-Token": "gw-secret",
                        },
                    ),
                    timeout=5,
                )
            except HTTPError as exc:
                assert exc.code == 401
            else:
                raise AssertionError("expected Content-Type refusal")
            assert len(_FakeMcp.seen_auth) == before
        finally:
            gateway.shutdown()
            writer = getattr(gateway, "cim_writer", None)
            if writer is not None:
                writer.stop()
            gateway.server_close()
    finally:
        upstream.shutdown()
        upstream.server_close()
