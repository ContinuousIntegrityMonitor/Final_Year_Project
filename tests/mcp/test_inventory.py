"""MCP artefact inventory digests and store writes (T-07)."""

from __future__ import annotations

import copy
from pathlib import Path

from cim.common.store import BaselineStore
from cim.mcp.inventory import (
    build_manifest,
    describe_tool,
    load_tools_list,
    synthetic_hexstrike_tools,
    tool_digest,
    write_inventory,
)
from cim.mcp.lab import MIN_HEXSTRIKE_TOOLS

TS = "2026-11-07T18:00:00Z"
HEXSTRIKE_LIST = Path(__file__).resolve().parents[2] / "corpora" / "mcp" / "tools_list.json"


def test_float_default_in_schema_still_hashes() -> None:
    tools = [
        {
            "name": "timed",
            "description": "Waits",
            "inputSchema": {
                "type": "object",
                "properties": {"execution_time": {"type": "number", "default": 1.5}},
            },
        }
    ]
    manifest, digests = build_manifest(
        server_id="hexstrike",
        name="hexstrike",
        description="HexStrike MCP",
        root="/opt/mcp/hexstrike",
        tools=tools,
        minimum=None,
    )
    assert "timed" in digests
    assert len(manifest.manifest_digest) == 64


def test_digests_stable_across_rereads() -> None:
    tools = synthetic_hexstrike_tools()
    first, digests_a = build_manifest(
        server_id="hexstrike",
        name="hexstrike",
        description="HexStrike MCP",
        root="/opt/mcp/hexstrike",
        tools=tools,
    )
    second, digests_b = build_manifest(
        server_id="hexstrike",
        name="hexstrike",
        description="HexStrike MCP",
        root="/opt/mcp/hexstrike",
        tools=copy.deepcopy(tools),
    )
    assert first.manifest_digest == second.manifest_digest
    assert digests_a == digests_b
    assert len(digests_a) == MIN_HEXSTRIKE_TOOLS


def test_one_description_change_flips_exactly_one_digest() -> None:
    tools = synthetic_hexstrike_tools()
    _, before = build_manifest(
        server_id="hexstrike",
        name="hexstrike",
        description="HexStrike MCP",
        root="/opt/mcp/hexstrike",
        tools=tools,
    )
    changed = copy.deepcopy(tools)
    changed[7]["description"] = "tampered description"
    _, after = build_manifest(
        server_id="hexstrike",
        name="hexstrike",
        description="HexStrike MCP",
        root="/opt/mcp/hexstrike",
        tools=changed,
    )
    flipped = [name for name in before if before[name] != after[name]]
    assert flipped == [changed[7]["name"]]


def test_full_hexstrike_inventory_stored(tmp_path: Path) -> None:
    tools = synthetic_hexstrike_tools()
    db = tmp_path / "baseline.db"
    with BaselineStore(db) as store:
        result = write_inventory(
            store,
            server_id="hexstrike",
            name="hexstrike",
            description="HexStrike MCP",
            root="/opt/mcp/hexstrike",
            origin="vm-mon",
            tools=tools,
            ts=TS,
        )
        status = store.verify_chain()
    assert len(result.tool_digests) == MIN_HEXSTRIKE_TOOLS
    assert len(result.tool_artefact_ids) == MIN_HEXSTRIKE_TOOLS
    # 1 server record + N tool records
    assert len(result.record_ids) == MIN_HEXSTRIKE_TOOLS + 1
    assert status.ok
    assert status.count == MIN_HEXSTRIKE_TOOLS + 1


def test_load_tools_list_round_trip(tmp_path: Path) -> None:
    import json

    path = tmp_path / "tools.json"
    tools = synthetic_hexstrike_tools(3)
    path.write_text(json.dumps({"tools": tools}), encoding="utf-8")
    loaded = load_tools_list(path)
    assert [t["name"] for t in loaded] == [t["name"] for t in tools]


def test_recorded_hexstrike_digests_do_not_move() -> None:
    # Values computed before contract 1.1 (org main @ 3ad014b). Stores keep these digests,
    # so a schema change that moves them makes every old store disagree with a new inventory.
    manifest, digests = build_manifest(
        server_id="hexstrike",
        name="hexstrike",
        description="HexStrike MCP",
        root="/opt/mcp/hexstrike",
        tools=load_tools_list(HEXSTRIKE_LIST),
    )
    assert manifest.manifest_digest == (
        "f937f478ce5a868fda30c3b11750b99e4c47fa0f987586e84c9e04b1bbb899b5"
    )
    assert digests["nmap_scan"] == (
        "14557bed90f0730242df51163ee8a46f4f956f27a7cf3ac2ae99f69e66abdc62"
    )


def test_fields_added_to_the_descriptor_do_not_change_its_digest() -> None:
    plain = describe_tool({"name": "t", "description": "d", "inputSchema": {"type": "object"}})
    filled = plain.model_copy(update={"tool_digest": "a" * 64})
    assert tool_digest(filled) == tool_digest(plain)
