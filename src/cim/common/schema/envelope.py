"""Event envelope shared by both collectors and the store (T-02)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cim.common.schema.alerts import ALERT_PAYLOADS
from cim.common.schema.canonical import canonical_json
from cim.common.schema.mcp import (
    McpArtefactPayload,
    McpBehaviourPayload,
    McpIntegrityPayload,
    McpPinPayload,
    McpSessionPayload,
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
# v1.1: three shapes share mcp_server + artefact; the payload's `record` picks one.
_MCP_ARTEFACT_RECORDS: dict[str, type[BaseModel]] = {
    "baseline": McpArtefactPayload,
    "session": McpSessionPayload,
    "pin": McpPinPayload,
}
# Which artefact types each listed alert code may sit under.
_ALERT_ARTEFACTS: dict[str, tuple[str, ...]] = {
    "proxy_malformed_frame": ("mcp_server",),
    "proxy_capture_failed": ("mcp_server",),
    "mcp_behaviour_drift": ("mcp_server", "mcp_tool"),
    "skill_behaviour_drift": ("skill",),
    "collector_restarted": ("monitor",),
    "collector_failed": ("monitor",),
}

_REQUIRED_IDS: dict[str, tuple[str, ...]] = {
    "skill": ("skill",),
    "mcp_server": ("server",),
    "mcp_tool": ("server", "tool"),
    "monitor": ("component",),  # v1.1: a CIM collector, for watchdog alerts (T-13)
}
_ID_FIELDS = ("server", "tool", "skill", "component")
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class Artefact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["mcp_server", "mcp_tool", "skill", "monitor"]
    server: str | None = None
    tool: str | None = None
    skill: str | None = None
    component: str | None = None

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
        if self.kind == "alert":
            self._check_alert()
        elif self.artefact.type == "skill" and self.kind in _SKILL_PAYLOADS:
            _SKILL_PAYLOADS[self.kind].model_validate(self.payload)
            if self.payload.get("skill_id") != self.artefact.skill:
                raise ValueError("payload skill_id does not match artefact.skill")
        elif self.artefact.type in ("mcp_server", "mcp_tool") and self.kind in _MCP_PAYLOADS:
            self._check_mcp()
        elif self.artefact.type == "monitor":
            raise ValueError("a monitor artefact carries alerts only")
        return self

    def _check_mcp(self) -> None:
        if self.kind == "behaviour" and self.artefact.type != "mcp_tool":
            raise ValueError("MCP behaviour events require artefact type mcp_tool")
        model = _MCP_PAYLOADS[self.kind]
        if self.kind == "artefact":
            record = self.payload.get("record", "baseline")  # v1.0 payloads have no record
            if not isinstance(record, str) or record not in _MCP_ARTEFACT_RECORDS:
                raise ValueError(f"unknown MCP artefact record: {record!r}")
            if record != "baseline" and self.artefact.type != "mcp_server":
                raise ValueError(f"an MCP {record} record belongs to an mcp_server artefact")
            model = _MCP_ARTEFACT_RECORDS[record]
        model.model_validate(self.payload)
        if self.payload.get("server_id") != self.artefact.server:
            raise ValueError("payload server_id does not match artefact.server")
        if self.artefact.type == "mcp_tool":
            if self.payload.get("tool_id") != self.artefact.tool:
                raise ValueError("payload tool_id does not match artefact.tool")
        elif self.kind == "artefact" and self.payload.get("tool_id") is not None:
            raise ValueError("mcp_server artefact payload must not set tool_id")

    def _check_alert(self) -> None:
        code = self.payload.get("code")
        if not isinstance(code, str) or not code:
            raise ValueError("an alert payload needs a string code")
        model = ALERT_PAYLOADS.get(code)
        if model is None:
            return  # a code this revision does not list yet
        model.model_validate(self.payload)
        if self.artefact.type not in _ALERT_ARTEFACTS[code]:
            raise ValueError(f"a {code} alert cannot belong to a {self.artefact.type} artefact")
        names = {
            "skill_id": self.artefact.skill,
            "server_id": self.artefact.server,
            "tool_id": self.artefact.tool if self.artefact.type == "mcp_tool" else None,
            "component": self.artefact.component,
        }
        for key, expected in names.items():
            if expected is not None and key in self.payload and self.payload[key] != expected:
                raise ValueError(f"payload {key} does not match the artefact")

    def payload_canonical(self) -> str:
        return canonical_json(self.payload)
