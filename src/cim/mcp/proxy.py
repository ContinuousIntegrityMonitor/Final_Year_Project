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
ADR-004).
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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Literal

from cim.common.schema.mcp import McpBehaviourPayload
from cim.common.store import BaselineStore
from cim.mcp.alert import score_latest
from cim.mcp.drift import diff_tools, pinned_tools, record_drift
from cim.mcp.envelope import record_observation
from cim.mcp.framing import Direction, parse_frame
from cim.mcp.inventory import hashable, write_inventory

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


CaptureEvent = ToolsSnapshot | CallCaptured | MalformedFrame


@dataclass(frozen=True)
class _Pending:
    method: str
    params: Any
    started_ns: int
    order: int


def digest(value: Any) -> str:
    """SHA-256 over sorted-key compact JSON. Floats allowed: only the digest is stored."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Capture:
    """Turns forwarded stdio lines into capture events. Pure: no I/O, no threads."""

    _TRACKED = frozenset({"tools/list", "tools/call"})

    def __init__(self, clock: Clock = time.monotonic_ns) -> None:
        self._clock = clock
        self._pending: dict[int | str, _Pending] = {}
        self._calls = 0

    def client_line(self, raw: bytes, started_ns: int | None = None) -> list[CaptureEvent]:
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
        self._pending[message_id] = _Pending(str(method), body.get("params"), started, order)
        return []

    def server_line(self, raw: bytes) -> list[CaptureEvent]:
        finished = self._clock()
        body = self._parse("server_to_client", raw)
        if isinstance(body, MalformedFrame):
            return [body]
        message_id = body.get("id")
        if not isinstance(message_id, int | str) or "method" in body:
            return []
        pending = self._pending.pop(message_id, None)
        if pending is None:
            return []
        if pending.method == "tools/list":
            result = body.get("result")
            tools = result.get("tools") if isinstance(result, dict) else None
            if isinstance(tools, list) and all(isinstance(t, dict) for t in tools):
                return [ToolsSnapshot(tools=tools)]
            return []
        return [self._call(pending, message_id, body, len(raw), finished)]

    def drain(self) -> list[CaptureEvent]:
        """Calls still waiting for a response when the session ends become timeouts."""
        events: list[CaptureEvent] = []
        now = self._clock()
        for message_id, pending in self._pending.items():
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
        except (UnicodeDecodeError, ValueError) as exc:
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
    ) -> None:
        self._store = store
        self._config = config
        self._now = now
        self._server_aid: int | None = None
        self._tool_aids: dict[str, int] = {}

    def apply(self, event: CaptureEvent) -> None:
        if isinstance(event, ToolsSnapshot):
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
                pin_id = self._store.append_artefact(
                    "mcp_pin", self._config.server_id, self._config.origin
                )
                self._store.append_record(
                    pin_id,
                    "artefact",
                    {
                        "code": "mcp_pin",
                        "server_id": self._config.server_id,
                        "name": self._config.server_id,
                        "tools": tools,
                    },
                    self._now(),
                )
            else:
                record_drift(
                    self._store,
                    server_id=self._config.server_id,
                    server_artefact_id=self._server_artefact(),
                    drifts=diff_tools(pin, tools),
                    ts=self._now(),
                )
        elif isinstance(event, CallCaptured):
            payload = McpBehaviourPayload(
                server_id=self._config.server_id,
                tool_id=event.tool,
                invocation_id=f"{event.order:06d}:{event.message_id}",
                request_digest=event.request_digest,
                response_digest=event.response_digest,
                binaries_executed=[],
                file_write_targets=[],
                egress=[],
                process_count=0,
                duration_us=event.duration_us,
                outcome=event.outcome,
            )
            self._store.append_record(
                self._tool_aid(event.tool),
                "behaviour",
                payload.model_dump(mode="json"),
                self._now(),
            )
            record_observation(
                self._store.path,
                server_id=self._config.server_id,
                tool=event.tool,
                arguments=event.arguments,
                result_size=event.response_size,
                outcome=event.outcome,
            )
            score_latest(
                self._store,
                artefact_id=self._server_artefact(),
                server_id=self._config.server_id,
                tool=event.tool,
                ts=self._now(),
            )
        else:
            self._store.append_record(
                self._server_artefact(),
                "alert",
                {
                    "code": "proxy_malformed_frame",
                    "direction": event.direction,
                    "reason": event.reason,
                    "sha256": event.sha256,
                    "size": event.size,
                },
                self._now(),
            )

    def _server_artefact(self) -> int:
        if self._server_aid is None:
            self._server_aid = self._store.append_artefact(
                "mcp_server", self._config.server_id, self._config.origin
            )
        return self._server_aid

    def _tool_aid(self, tool: str) -> int:
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
                _log(f"capture write failed: {exc}")


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
    """Run one proxied session. Returns the server's exit code."""
    if not command:
        raise ValueError("server command is required")
    capture = Capture(clock)
    lock = threading.Lock()
    events: queue.Queue[CaptureEvent | None] = queue.Queue()
    writer = threading.Thread(target=_write_events, args=(config, events), name="cim-proxy-store")
    writer.start()
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    server_in, server_out = child.stdin, child.stdout
    assert server_in is not None and server_out is not None

    def upstream() -> None:
        try:
            for line in client_in:
                # Register before forwarding: a fast server can answer before we return.
                with lock:
                    produced = capture.client_line(line, clock())
                try:
                    server_in.write(line)
                    server_in.flush()
                except OSError:
                    break
                for event in produced:
                    events.put(event)
        finally:
            try:
                server_in.close()
            except OSError:
                pass

    pump = threading.Thread(target=upstream, name="cim-proxy-upstream", daemon=True)
    pump.start()
    try:
        for line in server_out:
            client_out.write(line)
            client_out.flush()
            with lock:
                produced = capture.server_line(line)
            for event in produced:
                events.put(event)
    finally:
        code = child.wait()
        pump.join(timeout=1)
        with lock:
            for event in capture.drain():
                events.put(event)
        events.put(None)
        writer.join()
    return code
