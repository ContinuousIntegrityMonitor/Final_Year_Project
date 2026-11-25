"""MCP half of `cim status` and `cim events` (T-13 design note, section 7).

Hamza's territory (decision 7: "the MCP status summary and event descriptions"). This first
version was written with the shared commands so that C5 has both sides; it reads only the
chained records it is given, and can be replaced as a whole as long as `summarise` and
`event_label` keep their signatures.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from cim.common.store import StoredRecord
from cim.mcp.envelope import WARMUP

BEHAVIOUR_CODE = "mcp_behaviour_drift"


@dataclass(frozen=True)
class McpChange:
    record_id: int
    ts: str
    server_id: str
    tool_id: str | None  # None: a change to the server itself (its tool list)
    detail: str


@dataclass(frozen=True)
class McpSummary:
    servers: tuple[str, ...]  # every server the store names, in first-seen order
    tools: Mapping[str, tuple[str, ...]]  # server -> tool names in its latest baseline
    changes: tuple[McpChange, ...]  # drift records, oldest first
    behaviour_alerts: int
    calls: Mapping[tuple[str, str], int]  # (server, tool) -> chained calls

    @property
    def tool_count(self) -> int:
        return sum(len(names) for names in self.tools.values())

    def changed_artefacts(self) -> dict[tuple[str, str | None], list[McpChange]]:
        """Drift grouped by the artefact it changed: one rug pull is one entry (decision 6)."""
        grouped: dict[tuple[str, str | None], list[McpChange]] = {}
        for change in self.changes:
            grouped.setdefault((change.server_id, change.tool_id), []).append(change)
        return grouped

    def learning_tools(self) -> int:
        """Inventoried tools with fewer calls than the scorer's warm-up."""
        return sum(
            1
            for server, names in self.tools.items()
            for name in names
            if self.calls.get((server, name), 0) < WARMUP
        )


def summarise(records: Sequence[StoredRecord]) -> McpSummary:
    """What the MCP side of the store holds. Skill records are skipped."""
    servers: list[str] = []
    names: dict[str, tuple[str, ...]] = {}
    changes: list[McpChange] = []
    calls: dict[tuple[str, str], int] = {}
    behaviour_alerts = 0
    for record in records:
        payload = _payload(record)
        if payload is None:
            continue
        server = payload.get("server_id")
        if not isinstance(server, str):
            continue
        if server not in servers:
            servers.append(server)
        tool = payload.get("tool_id")
        tool_id = tool if isinstance(tool, str) else None
        if record.kind == "artefact":
            if payload.get("record", "baseline") == "baseline" and tool_id is None:
                tools = payload.get("tools")
                if isinstance(tools, list):
                    names[server] = tuple(
                        str(item.get("name")) for item in tools if isinstance(item, dict)
                    )
        elif record.kind == "integrity":
            detail = str(payload.get("detail") or payload.get("path") or "changed")
            changes.append(McpChange(record.id, record.ts, server, tool_id, detail))
        elif record.kind == "behaviour" and tool_id is not None:
            calls[(server, tool_id)] = calls.get((server, tool_id), 0) + 1
        elif record.kind == "alert":
            code = payload.get("code")
            behaviour_alerts += code == BEHAVIOUR_CODE
    return McpSummary(
        servers=tuple(servers),
        tools=names,
        changes=tuple(changes),
        behaviour_alerts=behaviour_alerts,
        calls=calls,
    )


def event_label(kind: str, payload: Mapping[str, Any]) -> str | None:
    """One line for an MCP record in `cim events`; None when the record is not an MCP one.

    Proxy alerts that omit ``server_id`` return None here so ``cim.common.status`` can
    word them from the artefact name (design note: side from artefact type).
    """
    server = payload.get("server_id")
    if not isinstance(server, str) or isinstance(payload.get("skill_id"), str):
        return None
    tool = payload.get("tool_id")
    where = f"{server}/{tool}" if isinstance(tool, str) else server
    if kind == "artefact":
        record = payload.get("record", "baseline")
        if record == "pin" or payload.get("code") == "mcp_pin":
            return f"{server}: fingerprint pinned"
        if record == "session":
            return f"{server}: session {payload.get('server_name', '')}".rstrip()
        tools = payload.get("tools")
        count = f" ({len(tools)} tools)" if isinstance(tools, list) and tool is None else ""
        return f"{where}: baseline{count}"
    if kind == "integrity":
        return f"{server}: {payload.get('detail') or payload.get('path') or 'changed'}"
    if kind == "behaviour":
        return f"{where}: call {payload.get('outcome', '')}".rstrip()
    if kind == "alert":
        text = payload.get("detail") or payload.get("reason") or ""
        return f"{where}: {payload.get('code', 'alert')}" + (f": {text}" if text else "")
    return None


def _payload(record: StoredRecord) -> dict[str, Any] | None:
    try:
        value = json.loads(record.payload)
    except ValueError:
        return None
    if not isinstance(value, dict) or isinstance(value.get("skill_id"), str):
        return None  # a skills record (MCP payloads may carry "skill_id": null)
    return value
