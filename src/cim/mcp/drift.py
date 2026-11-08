"""MCP schema-drift (rug-pull) detector (T-12).

Compares a fresh tools/list with the pinned list from the first time the server
was seen. A benign re-read produces nothing. A change produces one integrity
record per difference, naming the tool and, where a parameter moved, the
parameter. The pin is append-only: later lists never overwrite it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from cim.common.schema.mcp import McpIntegrityPayload
from cim.common.store import BaselineStore
from cim.mcp.inventory import describe_tool, tool_digest, tool_input_schema

Change = Literal["create", "modify", "delete"]
PIN_CODE = "mcp_pin"


@dataclass(frozen=True)
class Drift:
    """One human-readable difference against the pinned tool list."""

    tool: str
    change: Change
    detail: str


def _properties(tool: dict[str, Any]) -> dict[str, Any]:
    props = tool_input_schema(tool).get("properties", {})
    return props if isinstance(props, dict) else {}


def _param_type(schema: object) -> str:
    if isinstance(schema, dict) and isinstance(schema.get("type"), str):
        return str(schema["type"])
    return "unspecified"


def diff_tools(pinned: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[Drift]:
    """Diff two tools/list arrays. Empty means the schema is unchanged."""
    before = {str(tool["name"]): tool for tool in pinned}
    after = {str(tool["name"]): tool for tool in current}
    drifts: list[Drift] = []
    for name in sorted(set(before) | set(after)):
        old = before.get(name)
        new = after.get(name)
        if old is None and new is not None:
            drifts.append(Drift(name, "create", f"{name}: tool added"))
            continue
        if new is None and old is not None:
            drifts.append(Drift(name, "delete", f"{name}: tool removed"))
            continue
        assert old is not None and new is not None
        if describe_tool(old).description != describe_tool(new).description:
            drifts.append(Drift(name, "modify", f"{name}: description changed"))
        old_props = _properties(old)
        new_props = _properties(new)
        for param in sorted(set(new_props) - set(old_props)):
            drifts.append(
                Drift(
                    name,
                    "create",
                    f"{name}: added parameter {param} ({_param_type(new_props[param])})",
                )
            )
        for param in sorted(set(old_props) - set(new_props)):
            drifts.append(Drift(name, "delete", f"{name}: removed parameter {param}"))
        for param in sorted(set(old_props) & set(new_props)):
            old_type = _param_type(old_props[param])
            new_type = _param_type(new_props[param])
            if old_type != new_type:
                drifts.append(
                    Drift(
                        name, "modify", f"{name}: parameter {param} type {old_type} -> {new_type}"
                    )
                )
        already = any(item.tool == name for item in drifts)
        if not already and tool_digest(describe_tool(old)) != tool_digest(describe_tool(new)):
            drifts.append(Drift(name, "modify", f"{name}: schema changed"))
    return drifts


def pinned_tools(store: BaselineStore, server_id: str) -> list[dict[str, Any]] | None:
    """The first pinned tools/list for this server, or None if it was never seen."""
    for record in store.read_records():
        if record.kind != "artefact":
            continue
        payload = json.loads(record.payload)
        if payload.get("code") == PIN_CODE and payload.get("server_id") == server_id:
            tools = payload.get("tools")
            if isinstance(tools, list):
                return [tool for tool in tools if isinstance(tool, dict)]
    return None


def record_drift(
    store: BaselineStore,
    *,
    server_id: str,
    server_artefact_id: int,
    drifts: list[Drift],
    ts: str,
) -> int:
    """Append one integrity record per drift. Returns how many were written."""
    for drift in drifts:
        old_digest = None
        new_digest = None
        payload = McpIntegrityPayload(
            server_id=server_id,
            tool_id=drift.tool,
            change=drift.change,
            path=drift.detail,
            old_sha256=old_digest,
            new_sha256=new_digest,
        )
        store.append_record(
            server_artefact_id,
            "integrity",
            payload.model_dump(mode="json"),
            ts,
        )
    return len(drifts)
