"""Hamza polish from Fasih's verify notes + MCP demo beat smoke."""

from __future__ import annotations

import inspect
import os
import signal
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from cim.cli import app
from cim.common.schema.alerts import BehaviourAlertPayload, DriftFeature
from cim.common.store import BaselineStore
from cim.dashboard.board import load_board
from cim.dashboard.page import render_page
from cim.mcp.attacks import run_a1
from cim.mcp.cli import proxy
from cim.skills.inventory import take_inventory, write_baselines

runner = CliRunner()
REPO = Path(__file__).resolve().parents[2]


def test_proxy_help_escapes_toml_section_names() -> None:
    source = Path(inspect.getfile(proxy)).read_text(encoding="utf-8")
    assert "\\[mcp.servers.<id>]" in source
    assert "\\[store].path" in source
    result = runner.invoke(
        app, ["proxy", "--help"], env={**os.environ, "COLUMNS": "160", "NO_COLOR": "1"}
    )
    assert result.exit_code == 0
    text = result.stdout + result.stderr
    assert "mcp.servers" in text
    assert "store" in text


def test_a1_report_says_drift_records(tmp_path: Path) -> None:
    report = run_a1(tmp_path / "a1")
    assert report.passed
    rendered = report.render()
    assert "drift records:" in rendered
    assert "findings:" not in rendered


def test_dashboard_alerts_include_skills(tmp_path: Path) -> None:
    db = tmp_path / "both.sqlite"
    root = tmp_path / "skills"
    (root / "word-count").mkdir(parents=True)
    (root / "word-count" / "SKILL.md").write_text(
        "---\nname: word-count\ndescription: t\n---\n", encoding="utf-8"
    )
    with BaselineStore(db) as store:
        write_baselines(store, take_inventory([root]), ts="2026-11-28T00:00:00Z")
        aid = store.get_or_create_artefact("skill", "word-count", str(root / "word-count"))
        alert = BehaviourAlertPayload(
            code="skill_behaviour_drift",
            skill_id="word-count",
            observation_record_id=1,
            composite_milli=5000,
            features=[
                DriftFeature(
                    feature="destinations",
                    how="never_seen",
                    values=["private_ip:9"],
                    score_milli=5000,
                    threshold_milli=4000,
                )
            ],
            window=100,
            scorer_version=1,
            detail="destinations never seen: private_ip:9",
        )
        store.append_record(aid, "alert", alert.model_dump(mode="json"), "2026-11-28T00:00:01Z")
    board = load_board(db)
    page = render_page(board)
    assert board.skills is not None and board.skills.total_alerts >= 1
    # Static HTML stats card uses MCP + skills alerts.
    assert f"<b>{len(board.alerts) + board.skills.total_alerts}</b>" in page
    assert "Store loaded. No live demo MCP connection" in page
    # Demo-mode "Disconnected…" copy remains only inside the JS branch for data.demo.


def test_demo_mcp_beat_stand_in(tmp_path: Path) -> None:
    work = tmp_path / "beat"
    script = REPO / "scripts" / "demo_mcp_beat.py"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COV_", "COVERAGE_"))}
    done = subprocess.run(
        [sys.executable, str(script), "--work", str(work), "--no-pause", "all"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "PASS:" in done.stdout


def test_sigterm_handler_registered_on_run_gateway() -> None:
    """Source-level: run_gateway installs SIGTERM → KeyboardInterrupt (clears heartbeat)."""
    from cim.mcp import http_gateway

    source = Path(http_gateway.__file__).read_text(encoding="utf-8")
    assert "signal.SIGTERM" in source
    assert "KeyboardInterrupt" in source
    assert hasattr(signal, "SIGTERM")
