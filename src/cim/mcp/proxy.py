"""Transparent stdio MCP proxy with call capture (T-09).

The MCP client launches this proxy instead of the server. The proxy spawns the
real server as a child, forwards every stdio line byte-for-byte in both
directions, and records what it saw into the baseline store:

- ``tools/list`` responses -> server + tool artefact baselines (digests, T-07)
- ``tools/call`` request/response pairs -> one ``behaviour`` record per call
  (tool, order, request/response digests, duration, outcome)
- unparseable frames -> forwarded unchanged plus an ``alert`` record

Capture never alters forwarding: frames are forwarded byte-for-byte even when
they cannot be parsed, and store writes run on a separate thread (fail-open,
ADR-004). Fail-open is not fail-silent: a frame that capture could not handle,
and an event the store could not take, each leave a ``proxy_capture_failed``
alert, so a gap in the record is itself on the record.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Literal, cast

from cim.common.schema.mcp import McpBehaviourPayload, McpSessionPayload, ValueClass
from cim.common.store import BaselineStore
from cim.mcp.alert import score_latest
from cim.mcp.drift import (
    PIN_CODE,
    list_anomalies,
    list_digest,
    pinned_tools,
    record_drift,
    record_sweep,
    write_pin,
)
from cim.mcp.envelope import argument_shape, record_observation, value_classes
from cim.mcp.events import append_mcp
from cim.mcp.framing import Direction, parse_frame
from cim.mcp.inventory import hashable, sha256_canonical, write_inventory

Outcome = Literal["ok", "error", "timeout"]
Clock = Callable[[], int]


@dataclass(frozen=True)
class ProxyConfig:
    """Proxy settings. Every field can be set through the environment."""

    db: Path
    server_id: str = "hexstrike"
    origin: str = "vm-mon"
    root: str = "unknown"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ProxyConfig:
        source = os.environ if env is None else env
        return cls(
            db=Path(source.get("CIM_PROXY_DB", "logs/cim-store.sqlite")),
            server_id=source.get("CIM_PROXY_SERVER_ID", "hexstrike"),
            origin=source.get("CIM_PROXY_ORIGIN", "vm-mon"),
            root=source.get("CIM_PROXY_ROOT", "unknown"),
        )


@dataclass(frozen=True)
class ToolsSnapshot:
    tools: list[dict[str, Any]]


@dataclass(frozen=True)
class CallCaptured:
    order: int
    tool: str
    arguments: dict[str, Any]
    message_id: int | str
    request_digest: str
    response_digest: str | None
    response_size: int
    duration_us: int
    outcome: Outcome


@dataclass(frozen=True)
class MalformedFrame:
    direction: Direction
    reason: str
    size: int
    sha256: str


@dataclass(frozen=True)
class CaptureFailure:
    """A frame that was forwarded but that capture itself could not handle."""

    direction: Direction
    reason: str
    size: int
    sha256: str


@dataclass(frozen=True)
class SessionCaptured:
    """Result of one ``initialize`` handshake (contract 1.1 session record)."""

    server_name: str
    server_version: str
    protocol_version: str
    capabilities: dict[str, Any]


CaptureEvent = ToolsSnapshot | CallCaptured | MalformedFrame | CaptureFailure | SessionCaptured
_EVENT_NAMES = {
    ToolsSnapshot: "tools_list",
    CallCaptured: "tools_call",
    MalformedFrame: "malformed_frame",
    CaptureFailure: "capture_failure",
    SessionCaptured: "initialize",
}
FAILED_CODE = "proxy_capture_failed"


@dataclass(frozen=True)
class _Pending:
    method: str
    params: Any
    started_ns: int
    order: int


def digest(value: Any) -> str:
    """SHA-256 over sorted-key compact JSON. Floats allowed: only the digest is stored.

    JSON can carry a lone surrogate (an escape such as "\\ud800") that UTF-8 cannot.
    surrogatepass still gives such a value bytes, so any message can be digested.
    """
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _safe_text(value: object, limit: int = 300) -> str:
    """Text that can always be stored: unencodable characters replaced, length capped."""
    return str(value).encode("utf-8", "replace").decode("utf-8")[:limit]


class Capture:
    """Turns forwarded stdio lines into capture events. Pure: no I/O, no threads.

    Pending calls are keyed by ``(session, message_id)`` so two HTTP clients that
    reuse JSON-RPC ids do not overwrite each other (test report M3). Stdio keeps
    the default session ``""`` (one process, one Capture).
    """

    _TRACKED = frozenset({"tools/list", "tools/call", "initialize"})

    def __init__(self, clock: Clock = time.monotonic_ns) -> None:
        self._clock = clock
        self._pending: dict[tuple[str, int | str], _Pending] = {}
        self._calls = 0
        self._pages: dict[str, list[dict[str, Any]]] = {}

    def client_line(
        self,
        raw: bytes,
        started_ns: int | None = None,
        *,
        session: str = "",
    ) -> list[CaptureEvent]:
        started = self._clock() if started_ns is None else started_ns
        body = self._parse("client_to_server", raw)
        if isinstance(body, MalformedFrame):
            return [body]
        method = body.get("method")
        message_id = body.get("id")
        if method not in self._TRACKED or not isinstance(message_id, int | str):
            return []
        order = 0
        if method == "tools/call":
            self._calls += 1
            order = self._calls
        key = (session, message_id)
        self._pending[key] = _Pending(str(method), body.get("params"), started, order)
        return []

    def server_line(self, raw: bytes, *, session: str = "") -> list[CaptureEvent]:
        finished = self._clock()
        body = self._parse("server_to_client", raw)
        if isinstance(body, MalformedFrame):
            return [body]
        message_id = body.get("id")
        if not isinstance(message_id, int | str) or "method" in body:
            return []
        pending = self._pending.pop((session, message_id), None)
        if pending is None:
            return []
        if pending.method == "initialize":
            return self._session(body)
        if pending.method == "tools/list":
            result = body.get("result")
            tools = result.get("tools") if isinstance(result, dict) else None
            if not (isinstance(tools, list) and all(isinstance(t, dict) for t in tools)):
                return []
            # A long list arrives in pages. One page is not the list: comparing it with the
            # pin would report every tool on the other pages as removed.
            asked = pending.params if isinstance(pending.params, dict) else {}
            pages = self._pages.setdefault(session, [])
            if not asked.get("cursor"):
                pages.clear()  # this request starts the list from the beginning
            pages.extend(tools)
            more = result.get("nextCursor") if isinstance(result, dict) else None
            if isinstance(more, str) and more:
                return []
            whole = list(pages)
            pages.clear()
            return [ToolsSnapshot(tools=whole)]
        return [self._call(pending, message_id, body, len(raw), finished)]

    @staticmethod
    def _session(body: dict[str, Any]) -> list[CaptureEvent]:
        result = body.get("result")
        if not isinstance(result, dict):
            return []
        info = result.get("serverInfo")
        if not isinstance(info, dict):
            info = {}
        name = info.get("name")
        version = info.get("version")
        protocol = result.get("protocolVersion")
        caps = result.get("capabilities")
        return [
            SessionCaptured(
                server_name=name if isinstance(name, str) and name else "unknown",
                server_version=version if isinstance(version, str) and version else "unknown",
                protocol_version=(
                    protocol if isinstance(protocol, str) and protocol else "unknown"
                ),
                capabilities=caps if isinstance(caps, dict) else {},
            )
        ]

    def drain(self) -> list[CaptureEvent]:
        """Calls still waiting for a response when the session ends become timeouts."""
        events: list[CaptureEvent] = []
        now = self._clock()
        for (_session, message_id), pending in self._pending.items():
            if pending.method == "tools/call":
                events.append(self._call(pending, message_id, None, 0, now))
        self._pending.clear()
        return events

    def _call(
        self,
        pending: _Pending,
        message_id: int | str,
        response: dict[str, Any] | None,
        size: int,
        finished_ns: int,
    ) -> CallCaptured:
        params = pending.params if isinstance(pending.params, dict) else {}
        arguments = params.get("arguments")
        name = params.get("name")
        outcome: Outcome = "timeout"
        response_digest: str | None = None
        if response is not None:
            error = response.get("error")
            result = response.get("result")
            failed = error is not None or (isinstance(result, dict) and result.get("isError"))
            outcome = "error" if failed else "ok"
            response_digest = digest(error if error is not None else result)
        return CallCaptured(
            order=pending.order,
            tool=name if isinstance(name, str) and name else "unknown",
            arguments=arguments if isinstance(arguments, dict) else {},
            message_id=message_id,
            request_digest=digest(params),
            response_digest=response_digest,
            response_size=size,
            duration_us=max(0, (finished_ns - pending.started_ns) // 1000),
            outcome=outcome,
        )

    @staticmethod
    def _parse(direction: Direction, raw: bytes) -> dict[str, Any] | MalformedFrame:
        try:
            return parse_frame(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError) as exc:
            # RecursionError: JSON nested deeper than the parser will follow.
            return MalformedFrame(
                direction=direction,
                reason=type(exc).__name__,
                size=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
            )


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class StoreSink:
    """Writes capture events to the baseline store. Owned by one thread (SQLite)."""

    def __init__(
        self,
        store: BaselineStore,
        config: ProxyConfig,
        now: Callable[[], str] = _utc_now,
        *,
        session_id: str | None = None,
    ) -> None:
        self._store = store
        self._config = config
        self._now = now
        self._server_aid: int | None = None
        self._tool_aids: dict[str, int] = {}
        self._known_loaded = False
        # One id per proxy/gateway sink (one stdio session or one long-lived HTTP route).
        self._session_id = session_id if session_id is not None else uuid.uuid4().hex
        self._session_written = False

    def _load_known(self) -> None:
        """Find the artefact rows earlier sessions used for this server and its tools.

        Without this every proxy start added a new server row and a new row per tool, and
        one tool's records ended up spread over several artefact ids.
        """
        if self._known_loaded:
            return
        self._known_loaded = True
        for record in self._store.read_records():
            if record.kind not in ("artefact", "behaviour"):
                continue
            payload = json.loads(record.payload)
            if not isinstance(payload, dict) or payload.get("server_id") != self._config.server_id:
                continue
            if payload.get("code") == PIN_CODE:
                continue
            tool = payload.get("tool_id")
            if isinstance(tool, str):
                self._tool_aids.setdefault(tool, record.artefact_id)
            elif record.kind == "artefact" and self._server_aid is None:
                self._server_aid = record.artefact_id

    def record_failure(self, event: CaptureEvent, exc: BaseException) -> None:
        """Leave an alert for an event the store could not take.

        The message of the exception is cleaned before it is stored: it can quote the very
        text that made the write fail.
        """
        append_mcp(
            self._store,
            self._server_artefact(),
            artefact_type="mcp_server",
            server_id=self._config.server_id,
            kind="alert",
            payload={
                "code": FAILED_CODE,
                "stage": "store",
                "event": _EVENT_NAMES.get(type(event), "unknown"),
                "reason": type(exc).__name__,
                "detail": _safe_text(exc),
            },
            ts=self._now(),
        )

    def apply(self, event: CaptureEvent) -> None:
        if isinstance(event, SessionCaptured):
            if self._session_written:
                return
            session = McpSessionPayload(
                record="session",
                server_id=self._config.server_id,
                session_id=self._session_id,
                server_name=event.server_name,
                server_version=event.server_version,
                protocol_version=event.protocol_version,
                capabilities_digest=sha256_canonical(hashable(event.capabilities)),
            )
            append_mcp(
                self._store,
                self._server_artefact(),
                artefact_type="mcp_server",
                server_id=self._config.server_id,
                kind="artefact",
                payload=session,
                ts=self._now(),
            )
            self._session_written = True
        elif isinstance(event, ToolsSnapshot):
            tools = hashable(event.tools)
            pin = pinned_tools(self._store, self._config.server_id)
            if pin is None:
                result = write_inventory(
                    self._store,
                    server_id=self._config.server_id,
                    name=self._config.server_id,
                    description=f"{self._config.server_id} MCP server (seen by proxy)",
                    root=self._config.root,
                    origin=self._config.origin,
                    tools=tools,
                    ts=self._now(),
                    minimum=None,
                )
                self._server_aid = result.server_artefact_id
                self._tool_aids.update(result.tool_artefact_ids)
                write_pin(
                    self._store,
                    server_id=self._config.server_id,
                    origin=self._config.origin,
                    tools=tools,
                    ts=self._now(),
                    server_artefact_id=result.server_artefact_id,
                )
                # Nothing to compare a first list with, but it can be wrong on its own.
                record_drift(
                    self._store,
                    server_id=self._config.server_id,
                    server_artefact_id=result.server_artefact_id,
                    drifts=list_anomalies(tools),
                    ts=self._now(),
                    old_sha256=list_digest(tools),
                    new_sha256=list_digest(tools),
                )
            else:
                record_sweep(
                    self._store,
                    server_id=self._config.server_id,
                    server_artefact_id=self._server_artefact(),
                    pinned=pin,
                    current=tools,
                    ts=self._now(),
                )
        elif isinstance(event, CallCaptured):
            seq = event.order
            classes = cast(list[ValueClass], value_classes(event.arguments))
            behaviour = McpBehaviourPayload(
                server_id=self._config.server_id,
                tool_id=event.tool,
                invocation_id=f"{self._session_id}:{seq}",
                request_digest=event.request_digest,
                response_digest=event.response_digest,
                binaries_executed=[],
                file_write_targets=[],
                egress=[],
                process_count=0,
                duration_us=event.duration_us,
                outcome=event.outcome,
                response_bytes=event.response_size,
                session_id=self._session_id,
                seq=seq,
                argument_shape_digest=sha256_canonical(argument_shape(event.arguments)),
                value_classes=classes,
            )
            behaviour_id = append_mcp(
                self._store,
                self._tool_aid(event.tool),
                artefact_type="mcp_tool",
                server_id=self._config.server_id,
                tool_id=event.tool,
                kind="behaviour",
                payload=behaviour,
                ts=self._now(),
            )
            record_observation(
                self._store.path,
                server_id=self._config.server_id,
                tool=event.tool,
                arguments=event.arguments,
                result_size=event.response_size,
                outcome=event.outcome,
            )
            # T-16: score the row just written (finding 1). Fail-open on scorer faults.
            try:
                score_latest(
                    self._store,
                    artefact_id=self._server_artefact(),
                    server_id=self._config.server_id,
                    tool=event.tool,
                    ts=self._now(),
                    observation_record_id=behaviour_id,
                )
            except Exception as exc:  # noqa: BLE001 — scoring must never stop capture
                try:
                    append_mcp(
                        self._store,
                        self._server_artefact(),
                        artefact_type="mcp_server",
                        server_id=self._config.server_id,
                        kind="alert",
                        payload={
                            "code": FAILED_CODE,
                            "stage": "score",
                            "reason": "behaviour_score_failed",
                            "detail": str(exc)[:200],
                        },
                        ts=self._now(),
                    )
                except Exception:  # noqa: BLE001 — still fail-open
                    pass
        elif isinstance(event, CaptureFailure):
            append_mcp(
                self._store,
                self._server_artefact(),
                artefact_type="mcp_server",
                server_id=self._config.server_id,
                kind="alert",
                payload={
                    "code": FAILED_CODE,
                    "stage": "capture",
                    "direction": event.direction,
                    "reason": event.reason,
                    "sha256": event.sha256,
                    "size": event.size,
                },
                ts=self._now(),
            )
        else:
            append_mcp(
                self._store,
                self._server_artefact(),
                artefact_type="mcp_server",
                server_id=self._config.server_id,
                kind="alert",
                payload={
                    "code": "proxy_malformed_frame",
                    "direction": event.direction,
                    "reason": event.reason,
                    "sha256": event.sha256,
                    "size": event.size,
                },
                ts=self._now(),
            )

    def _server_artefact(self) -> int:
        self._load_known()
        if self._server_aid is None:
            self._server_aid = self._store.get_or_create_artefact(
                "mcp_server", self._config.server_id, self._config.origin
            )
        return self._server_aid

    def _tool_aid(self, tool: str) -> int:
        self._load_known()
        if tool not in self._tool_aids:
            self._tool_aids[tool] = self._store.append_artefact(
                "mcp_tool", tool, self._config.origin
            )
        return self._tool_aids[tool]


def _log(message: str) -> None:
    print(f"cim proxy: {message}", file=sys.stderr, flush=True)


def _write_events(config: ProxyConfig, events: queue.Queue[CaptureEvent | None]) -> None:
    try:
        config.db.parent.mkdir(parents=True, exist_ok=True)
        store = BaselineStore(config.db)
    except Exception as exc:  # noqa: BLE001 — capture is best-effort; forwarding continues
        _log(f"store unavailable, capture disabled: {exc}")
        while events.get() is not None:
            pass
        return
    with store:
        sink = StoreSink(store, config)
        while (event := events.get()) is not None:
            try:
                sink.apply(event)
            except Exception as exc:  # noqa: BLE001
                _log(f"capture write failed: {_safe_text(exc)}")
                try:
                    sink.record_failure(event, exc)
                except Exception as again:  # noqa: BLE001 — the store itself is failing
                    _log(f"could not record the failure either: {_safe_text(again)}")


def allow_call(body: dict[str, Any]) -> bool:
    """Enforcement hook. v1 allows everything; T-29 adds quarantine refusal here."""
    return True


def run_proxy(
    command: list[str],
    config: ProxyConfig,
    client_in: Iterable[bytes],
    client_out: IO[bytes],
    *,
    clock: Clock = time.monotonic_ns,
) -> int:
    """Run one proxied session. Returns the server's exit code.

    Registers ``<store>.run/sessions/proxy-<pid>.json`` for the session lifetime
    (T-13 decision 7) so ``cim status`` / ``cim watch`` can list live wrappers.
    """
    if not command:
        raise ValueError("server command is required")
    from cim.mcp.runtime import proxy_session

    with proxy_session(config.db, server_id=config.server_id, command=command):
        return _run_proxy_body(command, config, client_in, client_out, clock=clock)


def _run_proxy_body(
    command: list[str],
    config: ProxyConfig,
    client_in: Iterable[bytes],
    client_out: IO[bytes],
    *,
    clock: Clock,
) -> int:
    try:
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    except OSError as exc:
        # Nothing else has been started yet, so there is nothing left waiting.
        _log(f"cannot start the server: {exc}")
        return 127 if isinstance(exc, FileNotFoundError) else 126
    server_in, server_out = child.stdin, child.stdout
    assert server_in is not None and server_out is not None
    capture = Capture(clock)
    lock = threading.Lock()
    events: queue.Queue[CaptureEvent | None] = queue.Queue()
    writer = threading.Thread(target=_write_events, args=(config, events), name="cim-proxy-store")
    writer.start()

    def observe(direction: Direction, line: bytes, started_ns: int | None = None) -> None:
        """Capture one line. Whatever goes wrong here, forwarding carries on (ADR-004)."""
        try:
            with lock:
                if direction == "client_to_server":
                    produced = capture.client_line(line, started_ns)
                else:
                    produced = capture.server_line(line)
        except Exception as exc:  # noqa: BLE001
            produced = [
                CaptureFailure(
                    direction=direction,
                    reason=type(exc).__name__,
                    size=len(line),
                    sha256=hashlib.sha256(line).hexdigest(),
                )
            ]
        for event in produced:
            events.put(event)

    def upstream() -> None:
        try:
            for line in client_in:
                # Register before forwarding: a fast server can answer before we return.
                observe("client_to_server", line, clock())
                try:
                    server_in.write(line)
                    server_in.flush()
                except OSError:
                    break
        finally:
            try:
                server_in.close()
            except OSError:
                pass

    pump = threading.Thread(target=upstream, name="cim-proxy-upstream", daemon=True)
    pump.start()
    finished = False
    try:
        for line in server_out:
            client_out.write(line)
            client_out.flush()
            observe("server_to_client", line)
        finished = True
    finally:
        if not finished:
            child.terminate()  # we can no longer pass its output on (the client went away)
        code = child.wait()
        pump.join(timeout=1)
        try:
            with lock:
                drained = capture.drain()
        except Exception as exc:  # noqa: BLE001
            _log(f"could not close open calls: {_safe_text(exc)}")
            drained = []
        for event in drained:
            events.put(event)
        events.put(None)
        writer.join()
    return code
