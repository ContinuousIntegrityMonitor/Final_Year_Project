"""T-17 MCP attack pack (A1 rug-pull, A2 behavioural trigger)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cim.cli import app
from cim.common.status import load_status
from cim.mcp.attacks import run_a1, run_a2

runner = CliRunner()


def test_a1_rug_pull_records_schema_drift(tmp_path: Path) -> None:
    report = run_a1(tmp_path / "a1")
    assert report.passed, report.render()
    assert report.findings >= 1
    status = load_status(report.store)
    assert status.chain_ok
    assert any(f.side == "mcp" for f in status.findings)


def test_a2_trigger_writes_behaviour_alert(tmp_path: Path) -> None:
    report = run_a2(tmp_path / "a2", warmup=30)
    assert report.passed, report.render()
    assert report.alerts >= 1
    status = load_status(report.store)
    assert status.mcp.behaviour_alerts >= 1
    assert status.clean is False


def test_cli_mcp_attack_a1(tmp_path: Path) -> None:
    work = tmp_path / "work"
    result = runner.invoke(app, ["mcp-attack", "A1", "--work", str(work)])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


def test_cli_mcp_attack_a2(tmp_path: Path) -> None:
    work = tmp_path / "work"
    result = runner.invoke(app, ["mcp-attack", "A2", "--work", str(work), "--warmup", "30"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout
