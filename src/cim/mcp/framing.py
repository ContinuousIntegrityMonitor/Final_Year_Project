"""Newline-delimited JSON-RPC passthrough spike for the MCP proxy (T-04 → T-09)."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

Direction = Literal["client_to_server", "server_to_client"]
ReplyFn = Callable[[dict[str, Any]], dict[str, Any] | None]


@dataclass(frozen=True)
class Frame:
    """One logged stdio frame after a passthrough hop."""

    direction: Direction
    method: str | None
    message_id: int | str | None
    body: dict[str, Any]


def parse_frame(line: str) -> dict[str, Any]:
    """Parse one MCP stdio line. Frames are a single JSON object, no embedded newlines."""
    text = line.strip("\r\n")
    if not text:
        raise ValueError("empty frame")
    if "\n" in text:
        raise ValueError("frame must be a single line")
    body = json.loads(text)
    if not isinstance(body, dict):
        raise ValueError("frame must be a JSON object")
    return body


def encode_frame(body: dict[str, Any]) -> bytes:
    """Canonical single-line encoding used on the pipe (compact JSON + newline)."""
    return (json.dumps(body, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _frame_from(direction: Direction, body: dict[str, Any]) -> Frame:
    method = body.get("method")
    message_id = body.get("id")
    if method is not None and not isinstance(method, str):
        raise ValueError("method must be a string")
    if message_id is not None and not isinstance(message_id, int | str):
        raise ValueError("id must be an int or string")
    return Frame(direction=direction, method=method, message_id=message_id, body=body)


def session_through_pipe(
    requests: list[dict[str, Any]],
    reply_for: ReplyFn,
) -> list[Frame]:
    """Forward a client session across OS pipes and log both directions.

    The server side reads client frames, logs them, optionally writes a reply,
    and never rewrites the request body.
    """
    client_read, client_write = os.pipe()
    server_read, server_write = os.pipe()
    logged: list[Frame] = []
    errors: list[BaseException] = []

    def _server() -> None:
        try:
            with os.fdopen(client_read, "rb") as inbound, os.fdopen(server_write, "wb") as outbound:
                for raw in inbound:
                    body = parse_frame(raw.decode("utf-8"))
                    logged.append(_frame_from("client_to_server", body))
                    reply = reply_for(body)
                    if reply is None:
                        continue
                    logged.append(_frame_from("server_to_client", reply))
                    outbound.write(encode_frame(reply))
                    outbound.flush()
        except BaseException as exc:  # noqa: BLE001 — surfaced to the caller
            errors.append(exc)

    worker = threading.Thread(target=_server, name="cim-mcp-passthrough")
    worker.start()
    try:
        with os.fdopen(client_write, "wb") as outbound:
            for request in requests:
                outbound.write(encode_frame(request))
            outbound.flush()
        with os.fdopen(server_read, "rb") as inbound:
            replies = [parse_frame(line.decode("utf-8")) for line in inbound]
    finally:
        worker.join(timeout=5)
    if worker.is_alive():
        raise TimeoutError("passthrough server did not finish")
    if errors:
        raise errors[0]
    # replies were already logged inside the server thread; return the combined log
    _ = replies
    return logged
