"""MCP lab pin, host-only topology, and tool-inventory harness (T-04)."""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

LAB_NETWORK = ipaddress.ip_network("10.10.10.0/24")
MIN_HEXSTRIKE_TOOLS = 150
Role = Literal["monitor", "target", "listener"]


@dataclass(frozen=True)
class HexstrikePin:
    """Recorded HexStrike checkout for VM-MON."""

    repo: str
    ref: str
    sha: str
    recorded: str


@dataclass(frozen=True)
class LabNode:
    """One lab VM or listener on the host-only network."""

    name: str
    address: str
    role: Role
    default_route: str | None


@dataclass(frozen=True)
class LabTopology:
    """Host-only lab: no path from VMs onto the internet."""

    network: str
    internet_route: bool
    nodes: tuple[LabNode, ...]


def repo_root() -> Path:
    """Repository root (…/corpora/mcp/../../.. from this file is not used; walk parents)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("pyproject.toml not found above src/cim/mcp/lab.py")


def corpora_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "corpora" / "mcp"


def load_pin(path: Path | None = None) -> HexstrikePin:
    """Read corpora/mcp/hexstrike.pin (key=value lines)."""
    pin_path = path or (corpora_dir() / "hexstrike.pin")
    values: dict[str, str] = {}
    for raw in pin_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    missing = [key for key in ("repo", "ref", "sha", "recorded") if key not in values]
    if missing:
        raise ValueError(f"hexstrike pin missing fields: {', '.join(missing)}")
    sha = values["sha"]
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError(f"hexstrike sha must be 40 lowercase hex chars: {sha}")
    return HexstrikePin(
        repo=values["repo"],
        ref=values["ref"],
        sha=sha,
        recorded=values["recorded"],
    )


def load_topology(path: Path | None = None) -> LabTopology:
    """Read corpora/mcp/topology.json."""
    topo_path = path or (corpora_dir() / "topology.json")
    data = json.loads(topo_path.read_text(encoding="utf-8"))
    nodes_raw = data.get("nodes")
    if not isinstance(nodes_raw, list) or not nodes_raw:
        raise ValueError("topology.nodes must be a non-empty list")
    nodes: list[LabNode] = []
    for item in nodes_raw:
        if not isinstance(item, dict):
            raise ValueError("topology node must be an object")
        role = item.get("role")
        if role not in ("monitor", "target", "listener"):
            raise ValueError(f"unknown lab role: {role}")
        route = item.get("default_route")
        if route is not None and not isinstance(route, str):
            raise ValueError(f"default_route must be a string or null on {item.get('name')}")
        name = item.get("name")
        address = item.get("address")
        if not isinstance(name, str) or not isinstance(address, str):
            raise ValueError("node name and address must be strings")
        nodes.append(LabNode(name=name, address=address, role=role, default_route=route))
    network = data.get("network")
    if not isinstance(network, str):
        raise ValueError("topology.network must be a CIDR string")
    internet = data.get("internet_route")
    if not isinstance(internet, bool):
        raise ValueError("topology.internet_route must be a boolean")
    return LabTopology(network=network, internet_route=internet, nodes=tuple(nodes))


def assert_lab_isolated(topology: LabTopology) -> None:
    """VM-TGT stays inside the lab subnet and has no route off it.

    Raises ValueError when the recorded topology would make VM-TGT reachable
    from outside the host-only network.
    """
    network = ipaddress.ip_network(topology.network)
    if network != LAB_NETWORK:
        raise ValueError(f"lab network must be {LAB_NETWORK}, got {network}")
    if topology.internet_route:
        raise ValueError("lab must not route to the internet")
    targets = [node for node in topology.nodes if node.role == "target"]
    if not targets:
        raise ValueError("topology has no VM-TGT (role=target)")
    monitors = [node for node in topology.nodes if node.role == "monitor"]
    if not monitors:
        raise ValueError("topology has no VM-MON (role=monitor)")
    for node in topology.nodes:
        address = ipaddress.ip_address(node.address)
        if address not in network:
            raise ValueError(f"{node.name} address {node.address} is outside {network}")
        if node.default_route is None:
            continue
        gateway = ipaddress.ip_address(node.default_route)
        if gateway not in network:
            raise ValueError(
                f"{node.name} default route {node.default_route} leaves the lab subnet"
            )
    for target in targets:
        if target.default_route is not None:
            raise ValueError(
                f"{target.name} must have no default route so it is unreachable "
                "from outside the lab subnet"
            )


def tool_names(tools: list[dict[str, Any]]) -> list[str]:
    """Return tool names from an MCP tools/list payload."""
    names: list[str] = []
    for tool in tools:
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("each tool needs a non-empty name")
        names.append(name)
    return names


def enumerate_tools(
    tools: list[dict[str, Any]],
    *,
    minimum: int = MIN_HEXSTRIKE_TOOLS,
) -> list[str]:
    """Harness inventory. HexStrike acceptance requires at least 150 tools."""
    names = tool_names(tools)
    if len(names) < minimum:
        raise ValueError(f"expected at least {minimum} tools, got {len(names)}")
    if len(set(names)) != len(names):
        raise ValueError("tool names must be unique")
    return names


def rebuild_plan(pin: HexstrikePin, topology: LabTopology) -> str:
    """Ordered steps for a clean lab rebuild (operator runs these on the hypervisor)."""
    assert_lab_isolated(topology)
    lines = [
        f"1. Create a host-only network {topology.network} with internet_route=false.",
        "2. Provision VM-MON (Ubuntu 24.04) at the monitor address; no NAT.",
        f"3. Clone {pin.repo} and checkout {pin.sha} (ref {pin.ref}).",
        "4. Provision VM-TGT on the target address with no default route.",
        "5. Start the lab-internal listener on the listener address.",
        "6. Snapshot every VM. A scripted rebuild of these steps is the clean path.",
    ]
    return "\n".join(lines)


def check_recorded_lab(root: Path | None = None) -> str:
    """Validate the committed pin and topology. Returns the rebuild plan."""
    base = corpora_dir(root)
    pin = load_pin(base / "hexstrike.pin")
    topology = load_topology(base / "topology.json")
    return rebuild_plan(pin, topology)
