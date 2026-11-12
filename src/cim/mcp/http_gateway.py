"""HTTP / Streamable-HTTP MCP gateway (T-16b).

Cursor (or any HTTP MCP client) points at ``http://127.0.0.1:<port>/s/<id>/…``.
The gateway forwards the request to the configured upstream URL, returns the
upstream response byte-for-byte (status, headers that matter, body), and records
``tools/list`` / ``tools/call`` into the same baseline store path as the stdio
proxy (inventory, envelope, T-16 scorer).

Authorization and Cookie headers are forwarded and never written into the store.
Capture stores digests only (same as T-09). Optional ``authorization_env`` on a
route injects ``Authorization: Bearer <env>`` when the client did not send one
(for OAuth URL servers that Cursor cannot re-auth against localhost).
"""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.client import HTTPResponse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from cim.mcp.proxy import Capture, CaptureEvent, ProxyConfig, StoreSink, _utc_now

HopHeaders = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)

SECRET_REQUEST_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization"})


@dataclass(frozen=True)
class GatewayRoute:
    """One upstream MCP endpoint behind ``/s/<id>/``."""

    id: str
    upstream: str
    origin: str = "cursor"
    root: str = "cursor-http"
    authorization_env: str | None = None

    def proxy_config(self, db: Path) -> ProxyConfig:
        return ProxyConfig(db=db, server_id=self.id, origin=self.origin, root=self.root)


@dataclass(frozen=True)
class GatewayConfig:
    db: Path
    host: str
    port: int
    routes: tuple[GatewayRoute, ...]

    def route(self, server_id: str) -> GatewayRoute | None:
        for route in self.routes:
            if route.id == server_id:
                return route
        return None


def load_gateway_config(
    path: Path,
    *,
    db: Path | None = None,
    host: str | None = None,
    port: int | None = None,
) -> GatewayConfig:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("gateway config must be a JSON object")
    routes_raw = raw.get("routes")
    if not isinstance(routes_raw, list) or not routes_raw:
        raise ValueError("gateway config needs a non-empty routes array")
    routes: list[GatewayRoute] = []
    for item in routes_raw:
        if not isinstance(item, dict):
            raise ValueError("each route must be an object")
        rid = item.get("id")
        upstream = item.get("upstream")
        if not isinstance(rid, str) or not rid or "/" in rid:
            raise ValueError("route.id must be a non-empty string without '/'")
        if not isinstance(upstream, str) or not upstream:
            raise ValueError(f"route {rid!r} needs upstream URL")
        auth_env = item.get("authorization_env")
        if auth_env is not None and not isinstance(auth_env, str):
            raise ValueError(f"route {rid!r} authorization_env must be a string")
        routes.append(
            GatewayRoute(
                id=rid,
                upstream=upstream,
                origin=str(item.get("origin") or "cursor"),
                root=str(item.get("root") or f"cursor-{rid}"),
                authorization_env=auth_env,
            )
        )
    db_value = db or Path(str(raw.get("db") or "logs/cursor-http.sqlite"))
    host_value = host or str(raw.get("host") or "127.0.0.1")
    port_value = port if port is not None else int(raw.get("port") or 8877)
    return GatewayConfig(db=db_value, host=host_value, port=port_value, routes=tuple(routes))


def _log(message: str) -> None:
    print(f"cim http-gateway: {message}", file=sys.stderr, flush=True)


def _json_line(body: dict[str, Any]) -> bytes:
    return (json.dumps(body, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def parse_jsonrpc_bodies(raw: bytes, content_type: str) -> list[dict[str, Any]]:
    """Pull JSON-RPC objects from a JSON body or an SSE stream. Never raises."""
    if not raw:
        return []
    ctype = content_type.split(";", 1)[0].strip().lower()
    text = raw.decode("utf-8", errors="replace")
    out: list[dict[str, Any]] = []
    if "text/event-stream" in ctype:
        for block in text.split("\n\n"):
            data_lines: list[str] = []
            for line in block.splitlines():
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
            if not data_lines:
                continue
            payload = "\n".join(data_lines).strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                value = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                out.append(value)
            elif isinstance(value, list):
                out.extend(v for v in value if isinstance(v, dict))
        return out
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def join_upstream(upstream: str, remainder: str) -> str:
    """Map ``/s/<id>/<remainder>`` onto the upstream MCP URL."""
    rem = remainder.lstrip("/")
    if not rem:
        return upstream
    if rem.startswith("?"):
        sep = "&" if "?" in upstream else "?"
        return f"{upstream}{sep}{rem[1:]}"
    base = upstream if upstream.endswith("/") else f"{upstream}/"
    return urljoin(base, rem)


def filter_request_headers(
    headers: Mapping[str, str],
    *,
    authorization: str | None = None,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in HopHeaders:
            continue
        out[key] = value
    if authorization and not any(k.lower() == "authorization" for k in out):
        out["Authorization"] = authorization
    return out


def filter_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in HopHeaders:
            continue
        out[key] = value
    return out


class _RouteSession:
    def __init__(self, route: GatewayRoute, db: Path) -> None:
        self.route = route
        self.config = route.proxy_config(db)
        self.capture = Capture()
        self.lock = threading.Lock()


class _StoreWriter:
    def __init__(self, db: Path, routes: tuple[GatewayRoute, ...]) -> None:
        self._db = db
        self._routes = {r.id: r for r in routes}
        self._queue: queue.Queue[tuple[str, CaptureEvent] | None] = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, name="cim-http-gateway-store", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def put(self, server_id: str, event: CaptureEvent) -> None:
        self._queue.put((server_id, event))

    def stop(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=5)

    def _run(self) -> None:
        try:
            self._db.parent.mkdir(parents=True, exist_ok=True)
            from cim.common.store import BaselineStore

            store = BaselineStore(self._db)
        except Exception as exc:  # noqa: BLE001 — fail-open (ADR-004)
            _log(f"store unavailable, capture disabled: {exc}")
            while self._queue.get() is not None:
                pass
            return
        sinks: dict[str, StoreSink] = {}
        with store:
            while True:
                item = self._queue.get()
                if item is None:
                    return
                server_id, event = item
                route = self._routes.get(server_id)
                if route is None:
                    continue
                sink = sinks.get(server_id)
                if sink is None:
                    sink = StoreSink(store, route.proxy_config(self._db), now=_utc_now)
                    sinks[server_id] = sink
                try:
                    sink.apply(event)
                except Exception as exc:  # noqa: BLE001
                    _log(f"capture write failed ({server_id}): {exc}")


def _authorization_for(route: GatewayRoute, env: Mapping[str, str]) -> str | None:
    if not route.authorization_env:
        return None
    token = env.get(route.authorization_env, "").strip()
    if not token:
        return None
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def _capture_client(session: _RouteSession, bodies: list[dict[str, Any]]) -> list[CaptureEvent]:
    events: list[CaptureEvent] = []
    with session.lock:
        for body in bodies:
            events.extend(session.capture.client_line(_json_line(body)))
    return events


def _capture_server(session: _RouteSession, bodies: list[dict[str, Any]]) -> list[CaptureEvent]:
    events: list[CaptureEvent] = []
    with session.lock:
        for body in bodies:
            events.extend(session.capture.server_line(_json_line(body)))
    return events


def make_handler(
    config: GatewayConfig,
    sessions: dict[str, _RouteSession],
    writer: _StoreWriter,
    *,
    env: Mapping[str, str] | None = None,
    opener: Callable[..., Any] = urlopen,
) -> type[BaseHTTPRequestHandler]:
    source = os.environ if env is None else env

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            _log(f"{self.address_string()} {fmt % args}")

        def do_GET(self) -> None:  # noqa: N802
            self._proxy("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._proxy("POST")

        def do_DELETE(self) -> None:  # noqa: N802
            self._proxy("DELETE")

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._proxy("OPTIONS")

        def _proxy(self, method: str) -> None:
            parsed = urlsplit(self.path)
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) < 2 or parts[0] != "s":
                self.send_error(404, "use /s/<server-id>/…")
                return
            server_id = parts[1]
            route = config.route(server_id)
            if route is None:
                self.send_error(404, f"unknown server-id {server_id}")
                return
            remainder = "/".join(parts[2:])
            if parsed.query:
                remainder = f"{remainder}?{parsed.query}" if remainder else f"?{parsed.query}"
            upstream_url = join_upstream(route.upstream, remainder)

            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            session = sessions.setdefault(server_id, _RouteSession(route, config.db))
            req_bodies = parse_jsonrpc_bodies(body, self.headers.get("Content-Type", ""))
            for event in _capture_client(session, req_bodies):
                writer.put(server_id, event)

            headers = filter_request_headers(
                {k: v for k, v in self.headers.items()},
                authorization=_authorization_for(route, source),
            )
            request = Request(upstream_url, data=body if method != "GET" else None, method=method)
            for key, value in headers.items():
                request.add_header(key, value)

            try:
                with opener(request, timeout=120) as resp:
                    self._write_upstream(resp, session, writer, server_id)
            except HTTPError as exc:
                self._write_upstream(exc, session, writer, server_id)
            except URLError as exc:
                _log(f"upstream error {server_id}: {exc}")
                payload = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32000, "message": "upstream unreachable"},
                        "id": None,
                    }
                ).encode()
                self.send_response(502)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        def _write_upstream(
            self,
            resp: HTTPResponse | HTTPError,
            session: _RouteSession,
            store: _StoreWriter,
            server_id: str,
        ) -> None:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            for event in _capture_server(session, parse_jsonrpc_bodies(raw, ctype)):
                store.put(server_id, event)
            self.send_response(getattr(resp, "status", getattr(resp, "code", 502)))
            for key, value in filter_response_headers(dict(resp.headers.items())).items():
                if key.lower() in SECRET_REQUEST_HEADERS:
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    return Handler


def serve_gateway(
    config: GatewayConfig,
    *,
    env: Mapping[str, str] | None = None,
    opener: Callable[..., Any] = urlopen,
) -> ThreadingHTTPServer:
    sessions: dict[str, _RouteSession] = {}
    writer = _StoreWriter(config.db, config.routes)
    writer.start()
    handler = make_handler(config, sessions, writer, env=env, opener=opener)
    server = ThreadingHTTPServer((config.host, config.port), handler)
    server.cim_writer = writer  # type: ignore[attr-defined]
    server.cim_config = config  # type: ignore[attr-defined]
    server.cim_sessions = sessions  # type: ignore[attr-defined]
    return server


def run_gateway(config: GatewayConfig) -> int:
    server = serve_gateway(config)
    bound = server.server_address[1]
    ids = ", ".join(r.id for r in config.routes)
    _log(f"listening on http://{config.host}:{bound}/s/<id>/  routes=[{ids}] db={config.db}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log("shutting down")
    finally:
        writer: _StoreWriter | None = getattr(server, "cim_writer", None)
        sessions: dict[str, _RouteSession] = getattr(server, "cim_sessions", {})
        if writer is not None:
            for server_id, session in list(sessions.items()):
                with session.lock:
                    drained = session.capture.drain()
                for event in drained:
                    writer.put(server_id, event)
            time.sleep(0.05)
            writer.stop()
        server.server_close()
    return 0
