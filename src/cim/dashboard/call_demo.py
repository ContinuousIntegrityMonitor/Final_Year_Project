"""One real call from the dashboard button into the artificial MCP."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from cim.common.chain import compute_record_hash
from cim.common.store import BaselineStore
from cim.mcp.drift import pinned_tools
from cim.mcp.proxy import Capture, CaptureEvent, ProxyConfig, StoreSink

NORMAL_INPUT = {
    "to": "advisor@example.com",
    "subject": "Status",
    "body": "The monitor is watching.",
}
UNUSUAL_INPUT = {**NORMAL_INPUT, "bcc": "hidden@example.com"}


def session_path(db: Path) -> Path:
    return db.with_name(db.name + ".session")


def read_connected(db: Path) -> bool:
    path = session_path(db)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(data.get("connected"))


def write_connected(db: Path, connected: bool) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    session_path(db).write_text(
        json.dumps({"connected": connected}) + "\n",
        encoding="utf-8",
    )


def clear_demo(db: Path) -> dict[str, Any]:
    """Wipe the store and session so the demo can start from scratch."""
    db.parent.mkdir(parents=True, exist_ok=True)
    write_connected(db, False)
    if db.exists():
        con = sqlite3.connect(db, timeout=30)
        try:
            tables = [
                str(row[0])
                for row in con.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            for name in tables:
                con.execute(f'DELETE FROM "{name}"')
            con.commit()
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            con.close()
    else:
        with BaselineStore(db):
            pass
    for path in (Path(f"{db}-wal"), Path(f"{db}-shm")):
        try:
            path.unlink(missing_ok=True)
        except PermissionError:
            pass
    write_connected(db, False)
    return {"cleared": True, "connected": False}


def run_demo_call(db: Path, unusual: bool = False, *, connect_only: bool = False) -> dict[str, Any]:
    """Speak to the artificial server and record one step in the store."""
    if unusual and not _has_pin(db):
        run_demo_call(db, connect_only=True)
    env = os.environ.copy()
    env["CIM_DEMO_UNUSUAL"] = "0"
    server = Path(__file__).resolve().parents[1] / "mcp" / "demo_server.py"
    proc = subprocess.Popen(
        [sys.executable, str(server)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    assert proc.stdin is not None and proc.stdout is not None
    capture = Capture()
    events: list[CaptureEvent] = []
    arguments = UNUSUAL_INPUT if unusual else NORMAL_INPUT
    try:
        _roundtrip(
            proc,
            capture,
            events,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "cim-dashboard", "version": "0.1.0"},
                },
            },
        )
        listed = _roundtrip(
            proc, capture, events, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        called: dict[str, Any] = {"result": {}}
        if not connect_only:
            called = _roundtrip(
                proc,
                capture,
                events,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "send_email", "arguments": arguments},
                },
            )
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
    _apply(db, events)
    if unusual:
        _warn_behavior(db)
        write_connected(db, False)
    else:
        write_connected(db, True)
    result = listed.get("result")
    tools = result.get("tools") if isinstance(result, dict) else None
    schema: dict[str, Any] = {}
    if isinstance(tools, list) and tools and isinstance(tools[0], dict):
        raw_schema = tools[0].get("inputSchema")
        schema = raw_schema if isinstance(raw_schema, dict) else {}
    output = called.get("result")
    return {
        "tool": "send_email",
        "unusual": unusual,
        "connected": not unusual,
        "schema": schema,
        "input": {} if connect_only else arguments,
        "output": output if isinstance(output, dict) else {},
    }


def _roundtrip(
    proc: subprocess.Popen[bytes],
    capture: Capture,
    events: list[CaptureEvent],
    message: dict[str, Any],
) -> dict[str, Any]:
    assert proc.stdin is not None and proc.stdout is not None
    raw_in = (json.dumps(message) + "\n").encode()
    events.extend(capture.client_line(raw_in))
    proc.stdin.write(raw_in)
    proc.stdin.flush()
    raw_out = proc.stdout.readline()
    events.extend(capture.server_line(raw_out))
    parsed = json.loads(raw_out)
    if not isinstance(parsed, dict):
        raise RuntimeError("artificial MCP did not return an object")
    return parsed


def _warn_behavior(db: Path) -> None:
    """One warning for the different call, with the input and output change."""
    from datetime import UTC, datetime

    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with BaselineStore(db) as store:
        rows = store.read_records()
        if rows and "mcp_behaviour_drift" in rows[-1].payload:
            return
        artefact_id = (
            rows[-1].artefact_id
            if rows
            else store.append_artefact("mcp_server", "demo", "dashboard")
        )
        store.append_record(
            artefact_id,
            "alert",
            {
                "code": "mcp_behaviour_drift",
                "server_id": "demo",
                "tool_id": "send_email",
                "detail": "Strange behaviour detected.",
                "features": ["hidden copy"],
                "input_change": (
                    "Earlier input had to, subject, and body. "
                    "This input also has bcc set to a hidden address."
                ),
                "output_change": (
                    "Earlier output only said the mail was sent. "
                    "This output also names the hidden copy."
                ),
            },
            ts,
        )


def _has_pin(db: Path) -> bool:
    if not db.exists():
        return False
    with BaselineStore(db) as store:
        return pinned_tools(store, "demo") is not None


def tamper_log(db: Path) -> dict[str, Any]:
    """Rewrite the first log fingerprint so the next entry's link no longer matches.

    The edited row gets a fresh hash for its new payload. Later rows still name the
    old fingerprint, so verify-chain fails on the next entry. The MCP is disconnected.
    """
    if not db.exists():
        return {
            "tampered": False,
            "detail": "Nothing recorded yet. Connect and use the tool first.",
            "broken_at": None,
            "chain_ok": True,
            "connected": read_connected(db),
        }
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, kind, payload, prev_hash, record_hash FROM record ORDER BY id"
        ).fetchall()
        if len(rows) < 2:
            return {
                "tampered": False,
                "detail": "Need at least two log entries before a chain break can be shown.",
                "broken_at": None,
                "chain_ok": True,
                "connected": read_connected(db),
            }
        first = rows[0]
        new_payload = '{"tampered":true,"note":"demo rewrite of a past log entry"}'
        new_hash = compute_record_hash(str(first["prev_hash"]), str(first["kind"]), new_payload)
        con.execute(
            "UPDATE record SET payload = ?, record_hash = ? WHERE id = ?",
            (new_payload, new_hash, int(first["id"])),
        )
        con.commit()
    finally:
        con.close()
    write_connected(db, False)
    with BaselineStore(db) as store:
        chain = store.verify_chain()
    return {
        "tampered": True,
        "unusual": False,
        "detail": "An old log was changed.",
        "broken_at": chain.broken_at,
        "chain_ok": chain.ok,
        "chain_reason": chain.reason,
        "connected": False,
    }


def _apply(db: Path, events: list[CaptureEvent]) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    config = ProxyConfig(db=db, server_id="demo", origin="dashboard", root="artificial")
    with BaselineStore(db) as store:
        sink = StoreSink(store, config)
        for event in events:
            sink.apply(event)
