"""MCP schema-drift (rug-pull) detector (T-12).

Compares a fresh tools/list with the pinned list from the first time the server
was seen. A benign re-read produces nothing. A change produces one integrity
record per difference, naming the tool and, where a parameter moved, the
parameter. The pin is append-only: later lists never overwrite it.

The list comes from the server being watched, so nothing in it may stop the
comparison: an entry with no name, a name advertised twice, and a field this
module has never heard of are all differences to report, not errors.

A list state is reported once. Each record carries the digest of the list it
describes, and a list with the digest of the last report is not reported again.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from cim.common.schema.mcp import McpIntegrityPayload, McpPinPayload
from cim.common.store import BaselineStore
from cim.mcp.events import append_mcp
from cim.mcp.inventory import hashable

Change = Literal["create", "modify", "delete"]
PIN_CODE = "mcp_pin"
_SCHEMA_KEYS = ("inputSchema", "input_schema")
_OWN_MESSAGE = frozenset({"name", "description", *_SCHEMA_KEYS})  # reported in their own words
MATCHES_AGAIN = "tools/list matches the pinned list again"


@dataclass(frozen=True)
class Drift:
    """One human-readable difference against the pinned tool list."""

    tool: str | None  # None when the difference is about the list, not one named tool
    change: Change
    detail: str


def _canonical(value: Any) -> str:
    """One text per JSON value, so two values can be compared whatever their key order.

    ASCII-escaped on purpose: this has to work for any JSON a server can send, including
    text that is not valid Unicode, which the hashing rule for stored payloads may refuse.
    """
    return json.dumps(hashable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def list_digest(tools: list[dict[str, Any]]) -> str:
    """Digest of a whole tools/list. The order of the tools does not matter."""
    listing = "\n".join(sorted(_canonical(tool) for tool in tools))
    return hashlib.sha256(listing.encode("ascii")).hexdigest()


def _by_name(tools: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Group entries by name. Entries with no usable name are returned as canonical text."""
    named: dict[str, list[dict[str, Any]]] = {}
    unnamed: list[str] = []
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else None
        if isinstance(name, str) and name:
            named.setdefault(name, []).append(tool)
        else:
            unnamed.append(_canonical(tool))
    return named, sorted(unnamed)


def _schema(tool: dict[str, Any]) -> Any:
    return tool.get(_SCHEMA_KEYS[0], tool.get(_SCHEMA_KEYS[1]))


def _properties(schema: Any) -> dict[str, Any]:
    props = schema.get("properties") if isinstance(schema, dict) else None
    return props if isinstance(props, dict) else {}


def _param_type(schema: object) -> str:
    if isinstance(schema, dict) and isinstance(schema.get("type"), str):
        return str(schema["type"])
    return "unspecified"


def _diff_one(name: str, old: dict[str, Any], new: dict[str, Any]) -> list[Drift]:
    """Differences between two definitions of the same tool. Never raises on odd input."""
    drifts: list[Drift] = []
    if _canonical(old.get("description", "")) != _canonical(new.get("description", "")):
        drifts.append(Drift(name, "modify", f"{name}: description changed"))
    old_schema, new_schema = _schema(old), _schema(new)
    old_props, new_props = _properties(old_schema), _properties(new_schema)
    in_parameters: list[Drift] = []
    for param in sorted(set(new_props) - set(old_props)):
        kind = _param_type(new_props[param])
        in_parameters.append(Drift(name, "create", f"{name}: added parameter {param} ({kind})"))
    for param in sorted(set(old_props) - set(new_props)):
        in_parameters.append(Drift(name, "delete", f"{name}: removed parameter {param}"))
    for param in sorted(set(old_props) & set(new_props)):
        old_type, new_type = _param_type(old_props[param]), _param_type(new_props[param])
        if old_type != new_type:
            detail = f"{name}: parameter {param} type {old_type} -> {new_type}"
            in_parameters.append(Drift(name, "modify", detail))
    drifts += in_parameters
    if not in_parameters and _canonical(old_schema) != _canonical(new_schema):
        drifts.append(Drift(name, "modify", f"{name}: schema changed"))
    # Everything else a tool can carry (title, annotations, outputSchema, fields that do not
    # exist yet). A client may show any of it to the model, so any of it can carry an attack.
    for key in sorted((old.keys() | new.keys()) - _OWN_MESSAGE):
        if key not in old:
            drifts.append(Drift(name, "create", f"{name}: {key} added"))
        elif key not in new:
            drifts.append(Drift(name, "delete", f"{name}: {key} removed"))
        elif _canonical(old[key]) != _canonical(new[key]):
            drifts.append(Drift(name, "modify", f"{name}: {key} changed"))
    return drifts


def _times(count: int) -> str:
    return "once" if count == 1 else f"{count} times"


def list_anomalies(tools: list[dict[str, Any]]) -> list[Drift]:
    """What is wrong with a list on its own, before it is compared with anything."""
    named, unnamed = _by_name(tools)
    drifts = [
        Drift(name, "modify", f"{name}: advertised {_times(len(copies))}")
        for name, copies in sorted(named.items())
        if len(copies) > 1
    ]
    if unnamed:
        drifts.append(Drift(None, "modify", f"tools/list: {len(unnamed)} entries have no name"))
    return drifts


def diff_tools(pinned: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[Drift]:
    """Diff two tools/list arrays. Empty means nothing changed."""
    before, before_unnamed = _by_name(pinned)
    after, after_unnamed = _by_name(current)
    drifts: list[Drift] = []
    for name in sorted(before.keys() | after.keys()):
        old_copies, new_copies = before.get(name, []), after.get(name, [])
        if not old_copies:
            drifts.append(Drift(name, "create", f"{name}: tool added"))
            if len(new_copies) > 1:
                drifts.append(
                    Drift(name, "modify", f"{name}: advertised {_times(len(new_copies))}")
                )
            continue
        if not new_copies:
            drifts.append(Drift(name, "delete", f"{name}: tool removed"))
            continue
        old_texts = sorted(_canonical(copy) for copy in old_copies)
        if old_texts == sorted(_canonical(copy) for copy in new_copies):
            continue
        if len(new_copies) != len(old_copies):
            detail = (
                f"{name}: advertised {_times(len(new_copies))} "
                f"(pinned list had it {_times(len(old_copies))})"
            )
            drifts.append(Drift(name, "modify", detail))
        # A client may use any copy of a repeated name, so every copy is compared.
        reported: set[str] = set()
        for copy in new_copies:
            if _canonical(copy) in old_texts:
                continue
            for drift in _diff_one(name, old_copies[0], copy):
                if drift.detail not in reported:
                    reported.add(drift.detail)
                    drifts.append(drift)
    if after_unnamed != before_unnamed:
        detail = (
            f"tools/list: {len(after_unnamed)} entries have no name "
            f"(pinned list had {len(before_unnamed)})"
        )
        drifts.append(Drift(None, "modify", detail))
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


def write_pin(
    store: BaselineStore,
    *,
    server_id: str,
    origin: str,
    tools: list[dict[str, Any]],
    ts: str,
    server_artefact_id: int | None = None,
) -> None:
    """Pin a tools/list under the server's ``mcp_server`` artefact (contract 1.1).

    Older stores may still have a separate ``mcp_pin`` artefact row; ``pinned_tools``
    reads either shape by ``code``.
    """
    aid = server_artefact_id
    if aid is None:
        aid = server_artefact(store, server_id)
    if aid is None:
        aid = store.get_or_create_artefact("mcp_server", server_id, origin)
    payload = McpPinPayload(
        record="pin",
        server_id=server_id,
        name=server_id,
        tools=hashable(tools),
    )
    append_mcp(
        store,
        aid,
        artefact_type="mcp_server",
        server_id=server_id,
        kind="artefact",
        payload=payload,
        ts=ts,
    )


def server_artefact(store: BaselineStore, server_id: str) -> int | None:
    """The artefact row the server's inventory was written under, if there is one."""
    for record in store.read_records():
        if record.kind != "artefact":
            continue
        payload = json.loads(record.payload)
        if (
            payload.get("server_id") == server_id
            and payload.get("tool_id") is None
            and payload.get("code") != PIN_CODE
        ):
            return record.artefact_id
    return None


def _last_reported(store: BaselineStore, server_id: str) -> str | None:
    """Digest of the list state the newest integrity record for this server describes."""
    found: str | None = None
    for record in store.read_records():
        if record.kind != "integrity":
            continue
        payload = json.loads(record.payload)
        if payload.get("server_id") == server_id and isinstance(payload.get("new_sha256"), str):
            found = payload["new_sha256"]
    return found


def record_drift(
    store: BaselineStore,
    *,
    server_id: str,
    server_artefact_id: int,
    drifts: list[Drift],
    ts: str,
    old_sha256: str | None = None,
    new_sha256: str | None = None,
) -> int:
    """Append one integrity record per drift. Returns how many were written.

    old_sha256 and new_sha256 are list digests (see list_digest): the pinned list and the
    list these drifts were found in.
    """
    with store.transaction():
        for drift in drifts:
            # Contract 1.1: `path` holds a path-like id; words go in `detail`.
            path = drift.tool if drift.tool else "tools/list"
            payload = McpIntegrityPayload(
                server_id=server_id,
                tool_id=drift.tool,
                change=drift.change,
                path=path,
                detail=drift.detail,
                old_sha256=old_sha256,
                new_sha256=new_sha256,
            )
            append_mcp(
                store,
                server_artefact_id,
                artefact_type="mcp_server",
                server_id=server_id,
                kind="integrity",
                payload=payload,
                ts=ts,
            )
    return len(drifts)


def record_sweep(
    store: BaselineStore,
    *,
    server_id: str,
    server_artefact_id: int,
    pinned: list[dict[str, Any]],
    current: list[dict[str, Any]],
    ts: str,
) -> list[Drift]:
    """Compare a fresh list with the pin and record what is new. Returns what was recorded.

    A list in the state of the last report is not reported again. A list that has gone back
    to the pinned state is reported once, so a later change is new again.
    """
    pin_digest, now_digest = list_digest(pinned), list_digest(current)
    if now_digest == (_last_reported(store, server_id) or pin_digest):
        return []
    if now_digest == pin_digest:
        drifts = [Drift(None, "modify", MATCHES_AGAIN)]
    else:
        drifts = diff_tools(pinned, current) or [Drift(None, "modify", "tools/list changed")]
    record_drift(
        store,
        server_id=server_id,
        server_artefact_id=server_artefact_id,
        drifts=drifts,
        ts=ts,
        old_sha256=pin_digest,
        new_sha256=now_digest,
    )
    return drifts
