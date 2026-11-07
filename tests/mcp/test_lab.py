"""MCP lab pin, isolation, and tool harness (T-04)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cim.mcp.lab import (
    MIN_HEXSTRIKE_TOOLS,
    assert_lab_isolated,
    check_recorded_lab,
    enumerate_tools,
    load_pin,
    load_topology,
)


def test_recorded_pin_is_full_sha() -> None:
    pin = load_pin()
    assert pin.repo == "https://github.com/0x4m4/hexstrike-ai"
    assert pin.sha == "d689933ff579d839c676c82b231f8e98326c5f04"
    assert len(pin.sha) == 40


def test_recorded_topology_keeps_target_inside_lab() -> None:
    topology = load_topology()
    assert_lab_isolated(topology)
    targets = [node for node in topology.nodes if node.role == "target"]
    assert [node.name for node in targets] == ["VM-TGT"]
    assert targets[0].default_route is None
    plan = check_recorded_lab()
    assert "10.10.10.0/24" in plan
    assert pin_sha_in_plan(plan)


def pin_sha_in_plan(plan: str) -> bool:
    return "d689933ff579d839c676c82b231f8e98326c5f04" in plan


def test_target_with_outside_route_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "topology.json"
    path.write_text(
        json.dumps(
            {
                "network": "10.10.10.0/24",
                "internet_route": False,
                "nodes": [
                    {
                        "name": "VM-MON",
                        "address": "10.10.10.10",
                        "role": "monitor",
                        "default_route": None,
                    },
                    {
                        "name": "VM-TGT",
                        "address": "10.10.10.20",
                        "role": "target",
                        "default_route": "192.168.1.1",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="leaves the lab subnet"):
        assert_lab_isolated(load_topology(path))


def test_internet_route_rejected(tmp_path: Path) -> None:
    path = tmp_path / "topology.json"
    path.write_text(
        json.dumps(
            {
                "network": "10.10.10.0/24",
                "internet_route": True,
                "nodes": [
                    {
                        "name": "VM-MON",
                        "address": "10.10.10.10",
                        "role": "monitor",
                        "default_route": None,
                    },
                    {
                        "name": "VM-TGT",
                        "address": "10.10.10.20",
                        "role": "target",
                        "default_route": None,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="internet"):
        assert_lab_isolated(load_topology(path))


def test_harness_enumerates_at_least_150_tools() -> None:
    tools = [
        {"name": f"tool_{index:03d}", "description": "demo"} for index in range(MIN_HEXSTRIKE_TOOLS)
    ]
    names = enumerate_tools(tools)
    assert len(names) == MIN_HEXSTRIKE_TOOLS
    assert names[0] == "tool_000"


def test_harness_rejects_short_inventory() -> None:
    with pytest.raises(ValueError, match="at least 150"):
        enumerate_tools([{"name": "only_one"}])
