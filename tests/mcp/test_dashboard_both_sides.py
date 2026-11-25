"""Dashboard must show both MCP and Skills panels for the chosen board (U1 + T-16)."""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from urllib.request import urlopen

from typer.testing import CliRunner

from cim.cli import app
from cim.common.store import BaselineStore
from cim.dashboard.board import as_dict, load_board
from cim.dashboard.page import render_page
from cim.dashboard.serve import make_server
from cim.mcp.attacks import run_a1, run_a2
from cim.mcp.proxy import CallCaptured, ProxyConfig, StoreSink, ToolsSnapshot, digest
from cim.skills.corpus import default_root
from cim.skills.inventory import take_inventory, write_baselines

runner = CliRunner()
TS = "2026-11-25T18:00:00Z"
CLEAN = [
    {
        "name": "send_email",
        "description": "Send an email",
        "inputSchema": {
            "type": "object",
            "properties": {"to": {"type": "string"}},
            "required": ["to"],
        },
    }
]


def _mcp_and_skills_store(tmp_path: Path) -> Path:
    db = tmp_path / "both.sqlite"
    skills_root = tmp_path / "skills"
    shutil.copytree(default_root() / "word-count", skills_root / "word-count")
    with BaselineStore(db) as store:
        write_baselines(store, take_inventory([skills_root]), ts=TS)
        sink = StoreSink(store, ProxyConfig(db=db, server_id="mail"), now=lambda: TS)
        sink.apply(ToolsSnapshot(tools=CLEAN))
        sink.apply(
            CallCaptured(
                order=1,
                tool="send_email",
                arguments={"to": "10.10.10.20"},
                message_id=1,
                request_digest=digest({"to": "10.10.10.20"}),
                response_digest=digest({"ok": True}),
                response_size=20,
                duration_us=1000,
                outcome="ok",
            )
        )
    return db


def test_board_json_has_mcp_and_skills_sections(tmp_path: Path) -> None:
    db = _mcp_and_skills_store(tmp_path)
    board = load_board(db)
    payload = as_dict(board)
    assert board.chain_ok
    assert board.skills is not None
    assert any(row.skill_id == "word-count" for row in board.skills.skills)
    assert any(tool.name == "send_email" for tool in board.tools)
    assert payload["skills"] is not None
    assert payload["skills"]["summary"]["skills"] >= 1
    assert len(payload["tools"]) >= 1
    page = render_page(board)
    assert "Skills" in page
    assert "word-count" in page
    assert "send_email" in page


def test_dashboard_once_cli_shows_both_sides(tmp_path: Path) -> None:
    db = _mcp_and_skills_store(tmp_path)
    result = runner.invoke(app, ["dashboard", "--db", str(db), "--once"])
    assert result.exit_code == 0
    assert "send_email" in result.stdout
    assert "word-count" in result.stdout or "Skills" in result.stdout


def test_api_board_serves_skills_and_mcp(tmp_path: Path) -> None:
    db = _mcp_and_skills_store(tmp_path)
    server = make_server(db, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        with urlopen(f"http://{host}:{port}/api/board", timeout=5) as response:
            feed = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        thread.join(timeout=2)
    assert feed["chain_ok"] is True
    assert feed["skills"]["summary"]["skills"] >= 1
    assert any(t["name"] == "send_email" for t in feed["tools"])


def test_attack_stores_visible_on_dashboard(tmp_path: Path) -> None:
    a1 = run_a1(tmp_path / "a1")
    a2 = run_a2(tmp_path / "a2")
    assert a1.passed and a2.passed
    board_a1 = load_board(a1.store)
    board_a2 = load_board(a2.store)
    assert board_a1.changes, "A1 rug-pull should show schema changes on the board"
    assert board_a2.alerts or board_a2.patterns, "A2 should leave alert/pattern evidence"
    page = render_page(board_a2)
    assert "Record is safe" in page or "Something new" in page or "alert" in page.lower()
