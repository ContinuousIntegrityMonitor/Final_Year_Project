"""CI-runnable system smoke for the CLI."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from cim.cli import app

runner = CliRunner()


@pytest.mark.sys
def test_cim_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Continuous Integrity Monitor" in result.stdout


@pytest.mark.sys
def test_cim_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "cim" in result.stdout
