"""MCP artefact inventory: tools/list → digests → baseline store (T-07)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cim.common.schema.canonical import canonical_json
from cim.common.schema.mcp import McpArtefactPayload, McpToolDescriptor
from cim.common.store import BaselineStore
from cim.mcp.lab import MIN_HEXSTRIKE_TOOLS, enumerate_tools


def sha256_canonical(obj: Any) -> str:
    """SHA-256 hex digest of canonical JSON (no floats)."""
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()


def hashable(value: Any) -> Any:
    """Copy a JSON value so it can be hashed. Decimal numbers become strings."""
    if isinstance(value, float):
        return format(value, ".12g")
    if isinstance(value, dict):
        return {str(key): hashable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [hashable(item) for item in value]
    return value


def load_tools_list(path: Path) -> list[dict[str, Any]]:
    """Load a recorded MCP tools/list `tools` array from JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "tools" in data:
        tools = data["tools"]
    else:
        tools = data
    if not isinstance(tools, list):
        raise ValueError("tools/list JSON must be a list or an object with a tools array")
    for item in tools:
        if not isinstance(item, dict):
            raise ValueError("each tool must be an object")
    return tools


def synthetic_hexstrike_tools(count: int = MIN_HEXSTRIKE_TOOLS) -> list[dict[str, Any]]:
    """Deterministic stand-in inventory for CI when the live HexStrike process is offline."""
    if count < 1:
        raise ValueError("count must be >= 1")
    tools: list[dict[str, Any]] = []
    for i in range(count):
        tools.append(
            {
                "name": f"hexstrike_tool_{i:03d}",
                "description": f"HexStrike lab tool {i}",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "index": {"type": "integer"},
                    },
                    "required": ["target"],
                },
            }
        )
    return tools


def tool_input_schema(tool: dict[str, Any]) -> dict[str, Any]:
    schema = tool.get("inputSchema", tool.get("input_schema"))
    if schema is None:
        return {"type": "object", "properties": {}}
    if not isinstance(schema, dict):
        raise ValueError(f"inputSchema for {tool.get('name')!r} must be an object")
    return schema


def describe_tool(tool: dict[str, Any]) -> McpToolDescriptor:
    name = tool.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("each tool needs a non-empty name")
    description = tool.get("description", "")
    if not isinstance(description, str):
        raise ValueError(f"description for {name!r} must be a string")
    return McpToolDescriptor(
        name=name,
        description=description,
        input_schema_digest=sha256_canonical(hashable(tool_input_schema(tool))),
    )


def tool_digest(descriptor: McpToolDescriptor) -> str:
    """Stable per-tool digest over name + description + input schema digest."""
    return sha256_canonical(descriptor.model_dump(mode="json"))


def build_manifest(
    *,
    server_id: str,
    name: str,
    description: str,
    root: str,
    tools: list[dict[str, Any]],
    minimum: int | None = MIN_HEXSTRIKE_TOOLS,
) -> tuple[McpArtefactPayload, dict[str, str]]:
    """Return server artefact payload and map of tool name → tool digest."""
    if minimum is not None:
        enumerate_tools(tools, minimum=minimum)
    descriptors = [describe_tool(tool) for tool in tools]
    digests = {d.name: tool_digest(d) for d in descriptors}
    manifest_digest = sha256_canonical([d.model_dump(mode="json") for d in descriptors])
    payload = McpArtefactPayload(
        server_id=server_id,
        tool_id=None,
        name=name,
        description=description,
        root=root,
        tools=descriptors,
        manifest_digest=manifest_digest,
    )
    return payload, digests


@dataclass(frozen=True)
class InventoryResult:
    """Ids and digests produced by one inventory write."""

    server_artefact_id: int
    tool_artefact_ids: dict[str, int]
    tool_digests: dict[str, str]
    manifest_digest: str
    record_ids: tuple[int, ...]


def write_inventory(
    store: BaselineStore,
    *,
    server_id: str,
    name: str,
    description: str,
    root: str,
    origin: str,
    tools: list[dict[str, Any]],
    ts: str,
    minimum: int | None = MIN_HEXSTRIKE_TOOLS,
) -> InventoryResult:
    """Append server + per-tool artefact baselines into the store."""
    server_payload, digests = build_manifest(
        server_id=server_id,
        name=name,
        description=description,
        root=root,
        tools=tools,
        minimum=minimum,
    )
    record_ids: list[int] = []
    tool_artefact_ids: dict[str, int] = {}
    with store.transaction():
        server_aid = store.append_artefact("mcp_server", name, origin)
        record_ids.append(
            store.append_record(
                server_aid,
                "artefact",
                server_payload.model_dump(mode="json"),
                ts,
            )
        )
        for descriptor in server_payload.tools:
            tool_payload = McpArtefactPayload(
                server_id=server_id,
                tool_id=descriptor.name,
                name=descriptor.name,
                description=descriptor.description,
                root=root,
                tools=[descriptor],
                manifest_digest=server_payload.manifest_digest,
            )
            tool_aid = store.append_artefact("mcp_tool", descriptor.name, origin)
            tool_artefact_ids[descriptor.name] = tool_aid
            record_ids.append(
                store.append_record(
                    tool_aid,
                    "artefact",
                    tool_payload.model_dump(mode="json"),
                    ts,
                )
            )
    return InventoryResult(
        server_artefact_id=server_aid,
        tool_artefact_ids=tool_artefact_ids,
        tool_digests=digests,
        manifest_digest=server_payload.manifest_digest,
        record_ids=tuple(record_ids),
    )
