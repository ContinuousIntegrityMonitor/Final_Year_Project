"""Stdio passthrough spike (T-04)."""

from __future__ import annotations

from typing import Any

from cim.mcp.framing import session_through_pipe


def _reply(request: dict[str, Any]) -> dict[str, Any]:
    method = request["method"]
    message_id = request["id"]
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": message_id, "result": {"protocolVersion": "2024-11-05"}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "result": {"tools": [{"name": "nmap_scan"}]},
        }
    if method == "tools/call":
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "result": {"content": [{"type": "text", "text": "ok"}]},
        }
    raise AssertionError(method)


def test_passthrough_logs_full_client_session() -> None:
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "nmap_scan", "arguments": {"target": "10.10.10.20"}},
        },
    ]
    frames = session_through_pipe(requests, _reply)
    assert [frame.method for frame in frames if frame.direction == "client_to_server"] == [
        "initialize",
        "tools/list",
        "tools/call",
    ]
    assert [frame.message_id for frame in frames if frame.direction == "server_to_client"] == [
        1,
        2,
        3,
    ]
    # request bodies are logged unchanged
    assert frames[0].body == requests[0]
    call = next(frame for frame in frames if frame.method == "tools/call")
    assert call.body["params"]["arguments"]["target"] == "10.10.10.20"
    assert len(frames) == 6
