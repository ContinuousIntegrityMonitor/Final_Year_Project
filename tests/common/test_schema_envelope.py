"""Event envelope contract tests (T-02)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from cim.common.chain import compute_record_hash
from cim.common.schema import SCHEMA_VERSION
from cim.common.schema.canonical import canonical_json
from cim.common.schema.envelope import Artefact, Event

BEHAVIOUR: dict[str, Any] = {
    "skill_id": "pdf-tools",
    "invocation_id": "inv-0001",
    "cgroup_id": "cim-skill-pdf-tools-inv-0001.scope",
    "binaries_executed": ["/usr/bin/python3"],
    "file_write_targets": ["/tmp"],
    "egress": [{"dest_class": "private_ip", "port": 8080}],
    "process_count": 2,
    "duration_us": 1250000,
}
MCP_BEHAVIOUR: dict[str, Any] = {
    "server_id": "hexstrike",
    "tool_id": "nmap_scan",
    "invocation_id": "inv-mcp-0001",
    "request_digest": "a" * 64,
    "response_digest": "c" * 64,
    "binaries_executed": ["/usr/bin/nmap"],
    "file_write_targets": ["/tmp"],
    "egress": [{"dest_class": "public_ip", "port": 443}],
    "process_count": 1,
    "duration_us": 500000,
    "outcome": "ok",
}
MCP_SERVER_ARTEFACT: dict[str, Any] = {
    "server_id": "hexstrike",
    "tool_id": None,
    "name": "hexstrike",
    "description": "HexStrike MCP server",
    "root": "/opt/mcp/hexstrike",
    "tools": [
        {
            "name": "nmap_scan",
            "description": "Run nmap",
            "input_schema_digest": "a" * 64,
        }
    ],
    "manifest_digest": "b" * 64,
}
TS = "2026-10-19T10:00:00Z"


def skill_event(payload: dict[str, Any], skill: str = "pdf-tools") -> Event:
    return Event(
        ts=TS,
        artefact=Artefact(type="skill", skill=skill),
        kind="behaviour",
        payload=payload,
    )


def mcp_behaviour_event(payload: dict[str, Any], tool: str = "nmap_scan") -> Event:
    return Event(
        ts=TS,
        artefact=Artefact(type="mcp_tool", server="hexstrike", tool=tool),
        kind="behaviour",
        payload=payload,
    )


def test_round_trip() -> None:
    event = skill_event(BEHAVIOUR)
    assert Event.model_validate_json(event.model_dump_json()) == event


def test_mcp_behaviour_round_trip() -> None:
    event = mcp_behaviour_event(MCP_BEHAVIOUR)
    assert Event.model_validate_json(event.model_dump_json()) == event


def test_mcp_server_artefact_round_trip() -> None:
    event = Event(
        ts=TS,
        artefact=Artefact(type="mcp_server", server="hexstrike"),
        kind="artefact",
        payload=MCP_SERVER_ARTEFACT,
    )
    assert Event.model_validate_json(event.model_dump_json()) == event


def test_schema_version_matches_constant() -> None:
    assert skill_event(BEHAVIOUR).schema_version == SCHEMA_VERSION


def test_bad_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        Event(
            ts="yesterday",
            artefact=Artefact(type="skill", skill="pdf-tools"),
            kind="behaviour",
            payload=BEHAVIOUR,
        )


def test_float_rejected_in_any_payload() -> None:
    with pytest.raises(ValidationError):
        Event(
            ts=TS,
            artefact=Artefact(type="mcp_tool", server="hexstrike", tool="nmap_scan"),
            kind="behaviour",
            payload={"result_bytes": 1.5},
        )


def test_skill_payload_is_validated() -> None:
    with pytest.raises(ValidationError):
        skill_event({"skill_id": "pdf-tools"})


def test_skill_id_must_match_artefact() -> None:
    with pytest.raises(ValidationError):
        skill_event(BEHAVIOUR, skill="other-skill")


def test_mcp_tool_id_must_match_artefact() -> None:
    with pytest.raises(ValidationError):
        mcp_behaviour_event(MCP_BEHAVIOUR, tool="other-tool")


def test_mcp_server_id_must_match_artefact() -> None:
    with pytest.raises(ValidationError):
        Event(
            ts=TS,
            artefact=Artefact(type="mcp_tool", server="other-server", tool="nmap_scan"),
            kind="behaviour",
            payload=MCP_BEHAVIOUR,
        )


def test_mcp_behaviour_rejects_server_artefact() -> None:
    with pytest.raises(ValidationError):
        Event(
            ts=TS,
            artefact=Artefact(type="mcp_server", server="hexstrike"),
            kind="behaviour",
            payload=MCP_BEHAVIOUR,
        )


def test_mcp_server_artefact_rejects_tool_id() -> None:
    bad = dict(MCP_SERVER_ARTEFACT)
    bad["tool_id"] = "nmap_scan"
    with pytest.raises(ValidationError):
        Event(
            ts=TS,
            artefact=Artefact(type="mcp_server", server="hexstrike"),
            kind="artefact",
            payload=bad,
        )


def test_artefact_requires_identifiers() -> None:
    with pytest.raises(ValidationError):
        Artefact(type="mcp_tool", server="hexstrike")


def test_hash_independent_of_key_order() -> None:
    reordered = dict(reversed(list(BEHAVIOUR.items())))
    a = compute_record_hash("0" * 64, "behaviour", canonical_json(BEHAVIOUR))
    b = compute_record_hash("0" * 64, "behaviour", skill_event(reordered).payload_canonical())
    assert a == b
