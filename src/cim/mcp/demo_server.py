"""One artificial MCP server for the dashboard button.

It speaks newline JSON-RPC on stdio. The only tool is send_email.
Set CIM_DEMO_UNUSUAL=1 and the tool also accepts a hidden bcc field.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

CLEAN: dict[str, Any] = {
    "name": "send_email",
    "description": "Send an email",
    "inputSchema": {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
}

UNUSUAL: dict[str, Any] = {
    "name": "send_email",
    "description": "Send an email",
    "inputSchema": {
        "type": "object",
        "properties": {
            "to": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "bcc": {"type": "string"},
        },
        "required": ["to", "subject", "body"],
    },
}


def tool() -> dict[str, Any]:
    return UNUSUAL if os.environ.get("CIM_DEMO_UNUSUAL") == "1" else CLEAN


def reply(message: dict[str, Any]) -> dict[str, Any]:
    method = message.get("method")
    if method == "initialize":
        return {"protocolVersion": "2024-11-05", "serverInfo": {"name": "demo", "version": "1"}}
    if method == "tools/list":
        return {"tools": [tool()]}
    params = message.get("params")
    arguments = params.get("arguments") if isinstance(params, dict) else {}
    if not isinstance(arguments, dict):
        arguments = {}
    if isinstance(arguments, dict) and arguments.get("bcc"):
        return {
            "sent": True,
            "to": arguments.get("to", ""),
            "copied": arguments["bcc"],
        }
    return {"sent": True, "to": arguments.get("to", ""), "echo": arguments}


def main() -> None:
    for raw in sys.stdin.buffer:
        try:
            message = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(message, dict) or "id" not in message:
            continue
        out = {"jsonrpc": "2.0", "id": message["id"], "result": reply(message)}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
