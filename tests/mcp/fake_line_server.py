"""Minimal newline-delimited JSON-RPC server for proxy tests (not an MCP SDK server).

Tools: ``echo`` returns its arguments; ``garbage`` first writes a non-JSON line;
``fail`` returns a JSON-RPC error. Non-JSON input lines are ignored.
"""

from __future__ import annotations

import json
import sys

TOOLS = [
    {
        "name": "echo",
        "description": "Echo the arguments back",
        "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}},
    },
    {"name": "garbage", "description": "Emit a malformed frame", "inputSchema": {}},
    {"name": "fail", "description": "Always errors", "inputSchema": {}},
]


def reply(message: dict[str, object]) -> dict[str, object]:
    method = message.get("method")
    if method == "initialize":
        return {"protocolVersion": "2024-11-05", "serverInfo": {"name": "fake", "version": "1"}}
    if method == "tools/list":
        return {"tools": TOOLS}
    params = message.get("params")
    assert isinstance(params, dict)
    if params.get("name") == "garbage":
        sys.stdout.write("this line is not json\n")
    return {"content": [{"type": "text", "text": json.dumps(params.get("arguments"))}]}


def main() -> None:
    for raw in sys.stdin.buffer:
        try:
            message = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(message, dict) or "id" not in message:
            continue
        params = message.get("params")
        if isinstance(params, dict) and params.get("name") == "fail":
            out: dict[str, object] = {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {"code": -32000, "message": "boom"},
            }
        else:
            out = {"jsonrpc": "2.0", "id": message["id"], "result": reply(message)}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
