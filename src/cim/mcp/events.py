"""Append MCP records only after they pass the event contract (T-02 / contract 1.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from cim.common.schema.envelope import Artefact, Event, Kind
from cim.common.store import BaselineStore

ArtefactType = Literal["mcp_server", "mcp_tool"]


def append_mcp(
    store: BaselineStore,
    artefact_id: int,
    *,
    artefact_type: ArtefactType,
    server_id: str,
    kind: Kind,
    payload: BaseModel | dict[str, Any],
    ts: str,
    tool_id: str | None = None,
) -> int:
    """Validate through ``Event``, then append. Returns the new record id."""
    body = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else dict(payload)
    Event(
        ts=ts,
        artefact=Artefact(type=artefact_type, server=server_id, tool=tool_id),
        kind=kind,
        payload=body,
    )
    return store.append_record(artefact_id, kind, body, ts)
