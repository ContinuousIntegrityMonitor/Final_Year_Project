"""MCP stdio proxy collector (T-09): SYS-03 completeness, SYS-04 overhead, fail-open."""

from __future__ import annotations

import io
import json
import os
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.client.stdio import stdio_client
from mcp.types import TextContent

from cim.common.store import BaselineStore
from cim.mcp.proxy import Capture, ProxyConfig, allow_call, run_proxy
from mcp import ClientSession, StdioServerParameters

HERE = Path(__file__).resolve().parent
FAKE = [sys.executable, str(HERE / "fake_line_server.py")]


def _line(body: dict[str, Any]) -> bytes:
    return (json.dumps(body) + "\n").encode()


def _request(message_id: int, method: str, params: dict[str, Any] | None = None) -> bytes:
    return _line({"jsonrpc": "2.0", "id": message_id, "method": method, "params": params or {}})


def _call(message_id: int, name: str, arguments: dict[str, Any]) -> bytes:
    return _request(message_id, "tools/call", {"name": name, "arguments": arguments})


HANDSHAKE = [
    _request(1, "initialize", {"protocolVersion": "2024-11-05"}),
    _line({"jsonrpc": "2.0", "method": "notifications/initialized"}),
    _request(2, "tools/list"),
]


def _records(db: Path) -> list[tuple[str, dict[str, Any]]]:
    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT kind, payload FROM record ORDER BY id").fetchall()
    finally:
        con.close()
    return [(str(kind), json.loads(payload)) for kind, payload in rows]


def _proxy(db: Path, lines: list[bytes]) -> tuple[int, bytes]:
    out = io.BytesIO()
    code = run_proxy(FAKE, ProxyConfig(db=db, server_id="fake"), io.BytesIO(b"".join(lines)), out)
    return code, out.getvalue()


def test_scripted_replay_logs_100_calls_in_order(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    calls = [_call(100 + n, "echo", {"text": f"call {n}"}) for n in range(1, 101)]
    code, proxied = _proxy(db, HANDSHAKE + calls)
    direct = subprocess.run(FAKE, input=b"".join(HANDSHAKE + calls), capture_output=True).stdout

    assert code == 0
    assert proxied == direct  # transparent: byte-for-byte what the server wrote
    records = _records(db)
    behaviour = [p for kind, p in records if kind == "behaviour"]
    assert len(behaviour) == 100
    assert [p["invocation_id"] for p in behaviour] == [f"{n:06d}:{100 + n}" for n in range(1, 101)]
    assert {p["tool_id"] for p in behaviour} == {"echo"}
    assert {p["outcome"] for p in behaviour} == {"ok"}
    artefacts = [p for kind, p in records if kind == "artefact" and p.get("code") != "mcp_pin"]
    assert sorted(p["name"] for p in artefacts) == ["echo", "fail", "fake", "garbage"]
    with BaselineStore(db) as store:
        assert store.verify_chain().ok


def test_malformed_frames_are_forwarded_and_alerted(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    lines = HANDSHAKE + [
        b"this is not json from the client\n",
        b"\xff\xfe broken utf-8\n",
        _call(10, "garbage", {}),
        _call(11, "fail", {}),
        _call(12, "echo", {"ratio": 1.5}),
    ]
    code, proxied = _proxy(db, lines)

    assert code == 0
    assert b"this line is not json" in proxied
    records = _records(db)
    alerts = [p for kind, p in records if kind == "alert"]
    assert [a["direction"] for a in alerts] == [
        "client_to_server",
        "client_to_server",
        "server_to_client",
    ]
    assert {a["code"] for a in alerts} == {"proxy_malformed_frame"}
    outcomes = {p["tool_id"]: p["outcome"] for kind, p in records if kind == "behaviour"}
    assert outcomes == {"garbage": "ok", "fail": "error", "echo": "ok"}
    with BaselineStore(db) as store:
        assert store.verify_chain().ok


def test_unanswered_call_is_recorded_as_timeout() -> None:
    ticks = iter([0, 7_000_000])
    capture = Capture(clock=lambda: next(ticks))
    assert capture.client_line(_call(1, "echo", {"text": "x"})) == []
    (event,) = capture.drain()
    assert event.outcome == "timeout"  # type: ignore[union-attr]
    assert event.duration_us == 7_000  # type: ignore[union-attr]


def test_capture_overhead_p95_under_50ms() -> None:
    capture = Capture()
    reply = _line({"jsonrpc": "2.0", "id": 0, "result": {"content": []}})
    timings: list[float] = []
    for n in range(200):
        request = _call(n, "echo", {"text": "x" * 512})
        response = reply.replace(b'"id": 0', f'"id": {n}'.encode())
        started = time.perf_counter()
        capture.client_line(request)
        capture.server_line(response)
        timings.append(time.perf_counter() - started)
    assert statistics.quantiles(timings, n=20)[-1] < 0.050


def _round_trips(command: list[str], count: int) -> list[float]:
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    assert proc.stdin is not None and proc.stdout is not None
    timings: list[float] = []
    try:
        for n in range(count + 5):
            started = time.perf_counter()
            proc.stdin.write(_call(n, "echo", {"text": "ping"}))
            proc.stdin.flush()
            assert json.loads(proc.stdout.readline())["id"] == n
            if n >= 5:
                timings.append(time.perf_counter() - started)
    finally:
        proc.stdin.close()
        proc.wait(timeout=30)
    return timings


def test_added_latency_p95_under_50ms(tmp_path: Path) -> None:
    proxied_cmd = [sys.executable, "-m", "cim", "proxy", "--db", str(tmp_path / "s.sqlite"), "--"]
    direct = _round_trips(FAKE, 60)
    proxied = _round_trips(proxied_cmd + FAKE, 60)
    p95 = statistics.quantiles
    added = p95(proxied, n=20)[-1] - p95(direct, n=20)[-1]
    assert added <= 0.050, f"added p95 latency {added * 1000:.1f} ms"


def test_real_mcp_client_session_through_proxy(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "cim",
            "proxy",
            "--db",
            str(db),
            "--",
            sys.executable,
            str(HERE / "sdk_server.py"),
        ],
        env={**os.environ, "CIM_PROXY_SERVER_ID": "sdk"},
    )

    async def session() -> tuple[set[str], str]:
        with anyio.fail_after(60):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    listed = await client.list_tools()
                    result = await client.call_tool("add", {"a": 2, "b": 3})
        content = result.content[0]
        assert isinstance(content, TextContent)
        return {tool.name for tool in listed.tools}, content.text

    names, text = anyio.run(session)
    assert names == {"add", "shout"}
    assert text == "5"
    records = _records(db)
    calls = [p for kind, p in records if kind == "behaviour"]
    assert [(c["server_id"], c["tool_id"], c["outcome"]) for c in calls] == [("sdk", "add", "ok")]
    assert {p["name"] for kind, p in records if kind == "artefact"} >= {"add", "shout"}


def test_config_from_env(tmp_path: Path) -> None:
    config = ProxyConfig.from_env(
        {"CIM_PROXY_DB": str(tmp_path / "x.sqlite"), "CIM_PROXY_SERVER_ID": "hexstrike-2"}
    )
    assert config.db == tmp_path / "x.sqlite"
    assert config.server_id == "hexstrike-2"
    assert config.origin == "vm-mon"


def test_enforcement_hook_allows_everything_in_v1() -> None:
    assert allow_call({"method": "tools/call", "params": {"name": "anything"}})


def test_missing_server_command_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="server command"):
        run_proxy([], ProxyConfig(db=tmp_path / "s.sqlite"), io.BytesIO(), io.BytesIO())
