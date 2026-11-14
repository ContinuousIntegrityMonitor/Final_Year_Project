"""Event envelope shared by both collectors and the store (T-02)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cim.common.schema.canonical import canonical_json
from cim.common.schema.mcp import (
    McpArtefactPayload,
    McpBehaviourPayload,
    McpIntegrityPayload,
)
from cim.common.schema.skills import (
    SkillArtefactPayload,
    SkillBehaviourPayload,
    SkillIntegrityPayload,
)

Kind = Literal["artefact", "integrity", "behaviour", "alert"]

_SKILL_PAYLOADS: dict[str, type[BaseModel]] = {
    "artefact": SkillArtefactPayload,
    "integrity": SkillIntegrityPayload,
    "behaviour": SkillBehaviourPayload,
}

_MCP_PAYLOADS: dict[str, type[BaseModel]] = {
    "artefact": McpArtefactPayload,
    "integrity": McpIntegrityPayload,
    "behaviour": McpBehaviourPayload,
}

_REQUIRED_IDS: dict[str, tuple[str, ...]] = {
    "skill": ("skill",),
    "mcp_server": ("server",),
    "mcp_tool": ("server", "tool"),
}
_ID_FIELDS = ("server", "tool", "skill")
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class Artefact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["mcp_server", "mcp_tool", "skill"]
    server: str | None = None
    tool: str | None = None
    skill: str | None = None

    @model_validator(mode="after")
    def _check_ids(self) -> Self:
        required = _REQUIRED_IDS[self.type]
        missing = [f for f in required if getattr(self, f) is None]
        if missing:
            raise ValueError(f"artefact type {self.type!r} requires: {', '.join(missing)}")
        stray = [f for f in _ID_FIELDS if f not in required and getattr(self, f) is not None]
        if stray:
            raise ValueError(f"artefact type {self.type!r} must not set: {', '.join(stray)}")
        return self


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    ts: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    artefact: Artefact
    kind: Kind
    payload: dict[str, Any]

    @field_validator("ts")
    @classmethod
    def _check_ts(cls, value: str) -> str:
        datetime.strptime(value, _TS_FORMAT)  # the pattern fixes the shape; this rejects 99:99:99
        return value

    @model_validator(mode="after")
    def _check_payload(self) -> Self:
        canonical_json(self.payload)  # rejects floats and non-JSON types
        if self.artefact.type == "skill" and self.kind in _SKILL_PAYLOADS:
            _SKILL_PAYLOADS[self.kind].model_validate(self.payload)
            if self.payload.get("skill_id") != self.artefact.skill:
                raise ValueError("payload skill_id does not match artefact.skill")
        elif self.artefact.type in ("mcp_server", "mcp_tool") and self.kind in _MCP_PAYLOADS:
            if self.kind == "behaviour" and self.artefact.type != "mcp_tool":
                raise ValueError("MCP behaviour events require artefact type mcp_tool")
            _MCP_PAYLOADS[self.kind].model_validate(self.payload)
            if self.payload.get("server_id") != self.artefact.server:
                raise ValueError("payload server_id does not match artefact.server")
            if self.artefact.type == "mcp_tool":
                if self.payload.get("tool_id") != self.artefact.tool:
                    raise ValueError("payload tool_id does not match artefact.tool")
            elif self.kind == "artefact" and self.payload.get("tool_id") is not None:
                raise ValueError("mcp_server artefact payload must not set tool_id")
        return self

    def payload_canonical(self) -> str:
        return canonical_json(self.payload)
