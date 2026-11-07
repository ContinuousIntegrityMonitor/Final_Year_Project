"""Round-trip and contract tests for MCP-side payload models (T-02)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from cim.common.schema.mcp import (
    McpArtefactPayload,
    McpBehaviourPayload,
    McpEgress,
    McpIntegrityPayload,
    McpToolDescriptor,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64

SAMPLES: list[BaseModel] = [
    McpArtefactPayload(
        server_id="hexstrike",
        tool_id=None,
        name="hexstrike",
        description="HexStrike MCP server",
        root="/opt/mcp/hexstrike",
        tools=[
            McpToolDescriptor(
                name="nmap_scan",
                description="Run nmap",
                input_schema_digest=SHA_A,
            )
        ],
        manifest_digest=SHA_B,
    ),
    McpArtefactPayload(
        server_id="hexstrike",
        tool_id="nmap_scan",
        name="nmap_scan",
        description="Run nmap",
        root="/opt/mcp/hexstrike",
        tools=[
            McpToolDescriptor(
                name="nmap_scan",
                description="Run nmap",
                input_schema_digest=SHA_A,
            )
        ],
        manifest_digest=SHA_B,
    ),
    McpIntegrityPayload(
        server_id="hexstrike",
        tool_id="nmap_scan",
        change="modify",
        path="tools/nmap_scan.json",
        old_sha256=SHA_A,
        new_sha256=SHA_B,
    ),
    McpBehaviourPayload(
        server_id="hexstrike",
        tool_id="nmap_scan",
        invocation_id="inv-mcp-0001",
        request_digest=SHA_A,
        response_digest=SHA_C,
        binaries_executed=["/usr/bin/nmap"],
        file_write_targets=["/tmp"],
        egress=[McpEgress(dest_class="public_ip", port=443)],
        process_count=1,
        duration_us=500_000,
        outcome="ok",
    ),
]


def contains_float(obj: Any) -> bool:
    if isinstance(obj, float):
        return True
    if isinstance(obj, dict):
        return any(contains_float(v) for v in obj.values())
    if isinstance(obj, list):
        return any(contains_float(v) for v in obj)
    return False


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: type(s).__name__)
def test_round_trip(sample: BaseModel) -> None:
    again = type(sample).model_validate_json(sample.model_dump_json())
    assert again == sample


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: type(s).__name__)
def test_no_floats_in_payload(sample: BaseModel) -> None:
    assert not contains_float(sample.model_dump(mode="json"))


def test_float_rejected_for_integer_field() -> None:
    with pytest.raises(ValidationError):
        McpEgress(dest_class="private_ip", port=1.5)  # type: ignore[arg-type]


def test_bad_digest_rejected() -> None:
    with pytest.raises(ValidationError):
        McpToolDescriptor(name="x", description="y", input_schema_digest="not-a-digest")


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        McpIntegrityPayload.model_validate(
            {"server_id": "x", "change": "create", "path": "a", "surprise": 1}
        )


def test_invalid_outcome_rejected() -> None:
    with pytest.raises(ValidationError):
        McpBehaviourPayload.model_validate(
            {
                "server_id": "hexstrike",
                "tool_id": "nmap_scan",
                "invocation_id": "inv-1",
                "request_digest": SHA_A,
                "binaries_executed": [],
                "file_write_targets": [],
                "egress": [],
                "process_count": 0,
                "duration_us": 0,
                "outcome": "maybe",
            }
        )
