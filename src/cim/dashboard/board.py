"""Read a baseline store into the facts the status board shows."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cim.common.store import BaselineStore
from cim.mcp.envelope import ToolEnvelope, envelopes

_CALL_LIMIT = 40
_LINK_LIMIT = 18


@dataclass(frozen=True)
class PinnedTool:
    server_id: str
    name: str
    digest: str
    parameters: tuple[str, ...]
    schema: str = ""


@dataclass(frozen=True)
class ChainLink:
    """One bead on the fingerprint rail, in log order."""

    record_id: int
    mark: str
    label: str
    ts: str


@dataclass(frozen=True)
class SchemaChange:
    ts: str
    server_id: str
    tool: str
    detail: str


@dataclass(frozen=True)
class ToolCall:
    ts: str
    server_id: str
    tool: str
    outcome: str
    duration_us: int


@dataclass(frozen=True)
class FrameAlert:
    ts: str
    code: str
    detail: str
    input_change: str = ""
    output_change: str = ""


@dataclass(frozen=True)
class Board:
    """Everything the page can say about one store. Derived; nothing is written."""

    chain_ok: bool
    record_count: int
    broken_at: int | None
    chain_reason: str
    tools: tuple[PinnedTool, ...]
    changes: tuple[SchemaChange, ...]
    calls: tuple[ToolCall, ...]
    alerts: tuple[FrameAlert, ...]
    patterns: tuple[ToolEnvelope, ...]
    links: tuple[ChainLink, ...]
    earlier_links: int
    servers: tuple[str, ...]
    empty: bool


def load_board(db: Path) -> Board:
    """Open the store, recompute the chain, and collect the rows the page lists."""
    with BaselineStore(db) as store:
        chain = store.verify_chain()
        records = store.read_records()
    tools_by_server: dict[str, list[PinnedTool]] = {}
    params_by_server: dict[str, dict[str, tuple[str, ...]]] = {}
    schemas_by_server: dict[str, dict[str, str]] = {}
    changes: list[SchemaChange] = []
    calls: list[ToolCall] = []
    alerts: list[FrameAlert] = []
    links_all: list[ChainLink] = []
    servers: list[str] = []
    for record in records:
        payload = _object(record.payload)
        if payload is None:
            continue
        if payload.get("code") == "mcp_pin":
            _remember_server(servers, payload.get("server_id"))
            pinned = _pin_parameters(payload)
            if pinned is not None:
                params_by_server[pinned[0]] = pinned[1]
                schemas_by_server[pinned[0]] = pinned[2]
            links_all.append(ChainLink(record.id, "pin", "Fingerprint pinned", record.ts))
            continue
        server_id = payload.get("server_id")
        _remember_server(servers, server_id)
        if record.kind == "artefact" and payload.get("tool_id") is None:
            parsed = _pinned_tools(payload, params_by_server, schemas_by_server)
            if parsed is not None and isinstance(server_id, str):
                tools_by_server[server_id] = parsed
                links_all.append(ChainLink(record.id, "schema", "Schema recorded", record.ts))
        elif record.kind == "integrity":
            detail = _text(payload.get("path"))
            changes.append(
                SchemaChange(
                    ts=record.ts,
                    server_id=server_id if isinstance(server_id, str) else "",
                    tool=_text(payload.get("tool_id")),
                    detail=detail,
                )
            )
            links_all.append(ChainLink(record.id, "change", detail or "Schema changed", record.ts))
        elif record.kind == "behaviour":
            tool = _text(payload.get("tool_id")) or "unknown"
            calls.append(
                ToolCall(
                    ts=record.ts,
                    server_id=server_id if isinstance(server_id, str) else "",
                    tool=tool,
                    outcome=_text(payload.get("outcome")) or "unknown",
                    duration_us=_int(payload.get("duration_us")),
                )
            )
            links_all.append(ChainLink(record.id, "call", tool, record.ts))
        elif record.kind == "alert":
            detail = _alert_detail(payload)
            alerts.append(
                FrameAlert(
                    ts=record.ts,
                    code=_text(payload.get("code")) or "alert",
                    detail=detail,
                    input_change=_text(payload.get("input_change")),
                    output_change=_text(payload.get("output_change")),
                )
            )
            links_all.append(ChainLink(record.id, "alert", detail, record.ts))
    for server_id, known in params_by_server.items():
        schemas = schemas_by_server.get(server_id, {})
        tools_by_server[server_id] = [
            PinnedTool(
                server_id=tool.server_id,
                name=tool.name,
                digest=tool.digest,
                parameters=known.get(tool.name, tool.parameters),
                schema=schemas.get(tool.name, tool.schema),
            )
            for tool in tools_by_server.get(server_id, [])
        ]
    patterns: list[ToolEnvelope] = []
    if _has_envelope(db):
        for server_id in servers:
            patterns.extend(envelopes(db, server_id))
    tools = tuple(tool for server_id in servers for tool in tools_by_server.get(server_id, []))
    return Board(
        chain_ok=chain.ok,
        record_count=chain.count,
        broken_at=chain.broken_at,
        chain_reason=chain.reason,
        tools=tools,
        changes=tuple(reversed(changes)),
        calls=tuple(reversed(calls[-_CALL_LIMIT:])),
        alerts=tuple(reversed(alerts)),
        patterns=tuple(patterns),
        links=tuple(links_all[-_LINK_LIMIT:]),
        earlier_links=max(0, len(links_all) - _LINK_LIMIT),
        servers=tuple(servers),
        empty=chain.count == 0 and not patterns,
    )


def as_dict(board: Board) -> dict[str, Any]:
    """JSON the live page polls. Tuples become lists."""
    return {
        "chain_ok": board.chain_ok,
        "record_count": board.record_count,
        "broken_at": board.broken_at,
        "chain_reason": board.chain_reason,
        "empty": board.empty,
        "earlier_links": board.earlier_links,
        "servers": list(board.servers),
        "tools": [
            {
                "server_id": tool.server_id,
                "name": tool.name,
                "digest": tool.digest,
                "parameters": list(tool.parameters),
                "schema": tool.schema,
            }
            for tool in board.tools
        ],
        "changes": [
            {
                "ts": change.ts,
                "server_id": change.server_id,
                "tool": change.tool,
                "detail": change.detail,
            }
            for change in board.changes
        ],
        "calls": [
            {
                "ts": call.ts,
                "server_id": call.server_id,
                "tool": call.tool,
                "outcome": call.outcome,
                "duration_us": call.duration_us,
            }
            for call in board.calls
        ],
        "alerts": [
            {
                "ts": alert.ts,
                "code": alert.code,
                "detail": alert.detail,
                "input_change": alert.input_change,
                "output_change": alert.output_change,
            }
            for alert in board.alerts
        ],
        "patterns": [
            {
                "tool": pattern.tool,
                "observations": pattern.observations,
                "warmed_up": pattern.warmed_up,
                "call_count": pattern.call_count,
                "error_count": pattern.error_count,
                "value_classes": list(pattern.value_classes),
                "result_size_median": pattern.result_size_median,
            }
            for pattern in board.patterns
        ],
        "links": [
            {
                "record_id": link.record_id,
                "mark": link.mark,
                "label": link.label,
                "ts": link.ts,
            }
            for link in board.links
        ],
    }


def _remember_server(servers: list[str], server_id: object) -> None:
    if isinstance(server_id, str) and server_id not in servers:
        servers.append(server_id)


def _pin_parameters(
    payload: dict[str, Any],
) -> tuple[str, dict[str, tuple[str, ...]], dict[str, str]] | None:
    server_id = payload.get("server_id")
    raw = payload.get("tools")
    if not isinstance(server_id, str) or not isinstance(raw, list):
        return None
    named: dict[str, tuple[str, ...]] = {}
    schemas: dict[str, str] = {}
    for tool in raw:
        if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
            continue
        name = str(tool["name"])
        named[name] = _parameter_names(tool)
        schemas[name] = _schema_text(tool)
    return server_id, named, schemas


def _parameter_names(tool: dict[str, Any]) -> tuple[str, ...]:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        schema = tool.get("input_schema")
    props = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(props, dict):
        return ()
    return tuple(str(name) for name in props)


def _schema_text(tool: dict[str, Any]) -> str:
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        schema = tool.get("input_schema")
    if not isinstance(schema, dict):
        schema = {}
    shown = {
        "name": tool.get("name"),
        "description": tool.get("description", ""),
        "inputSchema": schema,
    }
    return json.dumps(shown, indent=2, sort_keys=True)


def _pinned_tools(
    payload: dict[str, Any],
    params_by_server: dict[str, dict[str, tuple[str, ...]]],
    schemas_by_server: dict[str, dict[str, str]],
) -> list[PinnedTool] | None:
    raw = payload.get("tools")
    server_id = payload.get("server_id")
    if not isinstance(raw, list) or not isinstance(server_id, str):
        return None
    known = params_by_server.get(server_id, {})
    schemas = schemas_by_server.get(server_id, {})
    tools: list[PinnedTool] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        digest = item.get("input_schema_digest")
        name = str(item["name"])
        tools.append(
            PinnedTool(
                server_id=server_id,
                name=name,
                digest=digest if isinstance(digest, str) else "",
                parameters=known.get(name, ()),
                schema=schemas.get(name, ""),
            )
        )
    return tools


def _alert_detail(payload: dict[str, Any]) -> str:
    detail = _text(payload.get("detail"))
    if detail:
        return detail
    reason = _text(payload.get("reason"))
    direction = _text(payload.get("direction"))
    if reason and direction:
        return f"{direction}: {reason}"
    return reason or direction or "unreadable frame"


def _has_envelope(db: Path) -> bool:
    con = sqlite3.connect(db)
    try:
        row = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'envelope_obs'"
        ).fetchone()
    finally:
        con.close()
    return row is not None


def _object(payload: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
