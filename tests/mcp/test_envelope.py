"""Behavioural envelope (T-14): deterministic features and warm-up."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from cim.cli import app
from cim.mcp.envelope import WARMUP, envelopes, record_observation

runner = CliRunner()
ARGS = {"to": "10.10.10.20", "body": "hello"}


def _replay(db: Path, count: int) -> None:
    for _ in range(count):
        record_observation(
            db,
            server_id="mail",
            tool="send_email",
            arguments=ARGS,
            result_size=40,
            outcome="ok",
        )


def test_two_replays_produce_identical_features(tmp_path: Path) -> None:
    first = tmp_path / "a.sqlite"
    second = tmp_path / "b.sqlite"
    _replay(first, 200)
    _replay(second, 200)
    left = envelopes(first, "mail")
    right = envelopes(second, "mail")
    assert left == right
    assert len(left) == 1
    assert left[0].warmed_up
    assert left[0].call_count == 100  # rolling window
    assert left[0].error_count == 0
    assert "private_ip" in left[0].value_classes
    assert left[0].result_size_median == 40


def test_warmup_opens_at_thirty_observations(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    _replay(db, WARMUP - 1)
    assert envelopes(db, "mail")[0].warmed_up is False
    record_observation(
        db, server_id="mail", tool="send_email", arguments=ARGS, result_size=40, outcome="ok"
    )
    assert envelopes(db, "mail")[0].warmed_up is True


def test_cli_shows_warmup_state(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    _replay(db, 5)
    result = runner.invoke(app, ["envelope", "--db", str(db), "--server-id", "mail"])
    assert result.exit_code == 0
    assert "warming_up 5/30" in result.stdout
    assert "send_email" in result.stdout
