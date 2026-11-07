"""MCP artefact inventory digests and store writes (T-07)."""

from __future__ import annotations

import copy
from pathlib import Path

from cim.common.store import BaselineStore
from cim.mcp.inventory import (
    build_manifest,
    load_tools_list,
    synthetic_hexstrike_tools,
    write_inventory,
)
from cim.mcp.lab import MIN_HEXSTRIKE_TOOLS

TS = "2026-11-07T18:00:00Z"


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
