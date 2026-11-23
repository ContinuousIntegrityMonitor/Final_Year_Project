"""Contract 1.1.0: additions to the T-02 event contract. Every 1.0 payload must still validate."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from cim.common.schema import CONTRACT_VERSION, SCHEMA_VERSION
from cim.common.schema.envelope import Artefact, Event
from cim.common.schema.mcp import McpBehaviourPayload, McpToolDescriptor

TS = "2026-11-24T10:00:00Z"
H = "a" * 64
SERVER = Artefact(type="mcp_server", server="hexstrike")
TOOL = Artefact(type="mcp_tool", server="hexstrike", tool="nmap_scan")
SKILL = Artefact(type="skill", skill="notes-sync")
MONITOR = Artefact(type="monitor", component="skills-watcher")


def event(artefact: Artefact, kind: str, payload: dict[str, Any]) -> Event:
    return Event(ts=TS, artefact=artefact, kind=kind, payload=payload)  # type: ignore[arg-type]


def behaviour(**extra: Any) -> dict[str, Any]:
    """The MCP behaviour payload as the proxy writes it today (1.0), plus any 1.1 fields."""
    return {
        "server_id": "hexstrike",
        "tool_id": "nmap_scan",
        "invocation_id": "000001:7",
        "request_digest": H,
        "response_digest": H,
        "binaries_executed": [],
        "file_write_targets": [],
        "egress": [],
        "process_count": 0,
        "duration_us": 1200,
        "outcome": "ok",
        **extra,
    }


def baseline(**extra: Any) -> dict[str, Any]:
    return {
        "server_id": "hexstrike",
        "name": "hexstrike",
        "description": "HexStrike MCP",
        "root": "/opt/mcp/hexstrike",
        "tools": [{"name": "nmap_scan", "description": "scan", "input_schema_digest": H}],
        "manifest_digest": H,
        **extra,
    }


def drift_alert(**extra: Any) -> dict[str, Any]:
    return {
        "code": "mcp_behaviour_drift",
        "server_id": "hexstrike",
        "tool_id": "nmap_scan",
        "observation_record_id": 812,
        "composite_milli": 10000,
        "features": [
            {
                "feature": "value_class",
                "how": "never_seen",
                "values": ["private_ip"],
                "score_milli": 10000,
                "threshold_milli": 4000,
            }
        ],
        "window": 100,
        "scorer_version": 1,
        "detail": "nmap_scan changed how it is used: value_class never seen: private_ip",
        **extra,
    }


def test_versions() -> None:
    assert CONTRACT_VERSION == "1.1.0"
    assert SCHEMA_VERSION == 1  # additions only: the event shape a 1.0 reader expects is unchanged


# --- 1.0 payloads still validate -------------------------------------------------------------


def test_v10_payloads_still_validate() -> None:
    event(TOOL, "behaviour", behaviour())
    event(SERVER, "artefact", baseline())  # no `record`: read as a baseline
    event(
        SERVER,
        "integrity",
        {"server_id": "hexstrike", "change": "modify", "path": "nmap_scan", "old_sha256": H},
    )
    event(SKILL, "alert", {"code": "anything_not_listed_yet"})  # unlisted codes pass


def test_proxy_alerts_as_written_today_already_conform() -> None:
    """The three alert shapes in cim/mcp/proxy.py validate under ProxyAlertPayload unchanged."""
    frame = {"direction": "server_to_client", "reason": "ValueError", "sha256": H, "size": 9}
    event(SERVER, "alert", {"code": "proxy_malformed_frame", **frame})
    event(SERVER, "alert", {"code": "proxy_capture_failed", "stage": "capture", **frame})
    event(
        SERVER,
        "alert",
        {
            "code": "proxy_capture_failed",
            "stage": "store",
            "event": "tools_call",
            "reason": "ValueError",
            "detail": "string is not valid Unicode text",
        },
    )


def test_behaviour_alert_as_written_today_does_not_conform_yet() -> None:
    """The 1.0 mcp_behaviour_drift shape (features as strings) moves to 1.1 in the scorer PR."""
    today = {
        "code": "mcp_behaviour_drift",
        "server_id": "hexstrike",
        "tool_id": "nmap_scan",
        "detail": "nmap_scan changed how it is used: value class private_ip",
        "features": ["value class private_ip"],
        "input_change": "Input now includes private_ip, which earlier calls did not.",
        "output_change": "Output size and result match earlier calls.",
    }
    with pytest.raises(ValidationError):
        event(SERVER, "alert", today)


# --- MCP behaviour (rows 1 and 2; scorer design section 6) -----------------------------------


def test_behaviour_v11_fields() -> None:
    event(
        TOOL,
        "behaviour",
        behaviour(
            invocation_id="sess-1:42",
            session_id="sess-1",
            seq=42,
            response_bytes=311,
            argument_shape_digest=H,
            value_classes=["other", "private_ip"],
        ),
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"session_id": "sess-1"},  # seq missing
        {"seq": 3},  # session_id missing
        {"session_id": "sess-1", "seq": 3},  # invocation_id is not sess-1:3
        {"seq": 0, "session_id": "s", "invocation_id": "s:0"},  # seq counts from 1
        {"response_bytes": -1},
        {"value_classes": ["private_ip", "other"]},  # not sorted
        {"value_classes": ["other", "other"]},  # repeated
        {"value_classes": ["hostname"]},  # not a value class
        {"argument_shape_digest": "nope"},
    ],
)
def test_behaviour_v11_rules(extra: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        McpBehaviourPayload.model_validate(behaviour(**extra))


# --- MCP artefact records (row 3; review P4, D3) ---------------------------------------------


def test_baseline_record_is_explicit_in_new_payloads() -> None:
    assert event(SERVER, "artefact", baseline(record="baseline")).payload["record"] == "baseline"
    tool = McpToolDescriptor(name="t", description="d", input_schema_digest=H, tool_digest=H)
    assert tool.tool_digest == H
    with pytest.raises(ValidationError):
        McpToolDescriptor(name="t", description="d", input_schema_digest=H, tool_digest="x")


def test_session_record() -> None:
    session = {
        "record": "session",
        "server_id": "hexstrike",
        "session_id": "sess-1",
        "server_name": "hexstrike-ai",
        "server_version": "6.0",
        "protocol_version": "2025-03-26",
        "capabilities_digest": H,
    }
    event(SERVER, "artefact", session)
    with pytest.raises(ValueError, match="belongs to an mcp_server"):
        event(TOOL, "artefact", {**session, "tool_id": "nmap_scan"})


def test_pin_record_takes_any_tool_object() -> None:
    tools = [{"name": "nmap_scan", "inputSchema": {"type": "object"}, "annotations": {"x": True}}]
    pin = {"record": "pin", "server_id": "hexstrike", "name": "hexstrike", "tools": tools}
    assert event(SERVER, "artefact", pin).payload["tools"] == tools


def test_unknown_record_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown MCP artefact record"):
        event(SERVER, "artefact", baseline(record="snapshot"))


def test_integrity_detail() -> None:
    detail = "nmap_scan: description changed"
    payload = {"server_id": "hexstrike", "change": "modify", "path": "nmap_scan", "detail": detail}
    assert event(SERVER, "integrity", payload).payload["detail"] == detail


# --- Alerts (row 4; scorer design section 7; T-13 design section 6) --------------------------


def test_alert_needs_a_code() -> None:
    with pytest.raises(ValueError, match="string code"):
        event(SERVER, "alert", {"reason": "x"})


def test_behaviour_alerts_on_both_sides() -> None:
    event(SERVER, "alert", drift_alert())
    event(TOOL, "alert", drift_alert())
    skill = drift_alert(code="skill_behaviour_drift", skill_id="notes-sync")
    del skill["server_id"], skill["tool_id"]
    event(SKILL, "alert", skill)


@pytest.mark.parametrize(
    ("artefact", "payload", "message"),
    [
        (SERVER, drift_alert(skill_id="notes-sync"), "server_id and tool_id only"),
        (SKILL, drift_alert(), "cannot belong to a skill artefact"),
        (SERVER, drift_alert(server_id="other"), "server_id does not match"),
        (TOOL, drift_alert(tool_id="other_tool"), "tool_id does not match"),
        (SERVER, drift_alert(features=[]), "at least 1"),
        (SERVER, drift_alert(composite_milli="10000"), "valid integer"),
    ],
)
def test_behaviour_alert_rules(artefact: Artefact, payload: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        event(artefact, "alert", payload)


def test_behaviour_alert_carries_at_most_three_features() -> None:
    feature = drift_alert()["features"][0]
    with pytest.raises(ValidationError):
        event(SERVER, "alert", drift_alert(features=[feature] * 4))


def test_monitor_artefact_and_alerts() -> None:
    restart = {
        "code": "collector_restarted",
        "reason": "exited",
        "component": "skills-watcher",
        "exit_code": -9,
        "gap_s": 1,
        "restarts": 1,
    }
    event(MONITOR, "alert", restart)
    with pytest.raises(ValueError, match="component does not match"):
        event(MONITOR, "alert", {**restart, "component": "http-gateway"})
    with pytest.raises(ValueError, match="cannot belong to a mcp_server"):
        event(SERVER, "alert", restart)
    with pytest.raises(ValueError, match="alerts only"):
        event(MONITOR, "behaviour", {"anything": 1})
    with pytest.raises(ValueError, match="requires: component"):
        Artefact(type="monitor")
    with pytest.raises(ValueError, match="must not set: component"):
        Artefact(type="skill", skill="x", component="y")
