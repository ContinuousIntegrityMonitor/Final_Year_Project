"""Behaviour alert after warm-up (T-16, MCP half)."""

from __future__ import annotations

from pathlib import Path

from cim.common.store import BaselineStore
from cim.mcp.alert import score_latest
from cim.mcp.envelope import WARMUP, record_observation

TS = "2026-11-11T12:00:00Z"


def _fill(store: BaselineStore, aid: int, count: int, arguments: dict[str, str]) -> None:
    for _ in range(count):
        record_observation(
            store.path,
            server_id="demo",
            tool="send_email",
            arguments=arguments,
            result_size=20,
            outcome="ok",
        )
        score_latest(store, artefact_id=aid, server_id="demo", tool="send_email", ts=TS)


def test_warmup_does_not_alert(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    with BaselineStore(db) as store:
        aid = store.append_artefact("mcp_server", "demo", "dashboard")
        _fill(store, aid, WARMUP, {"body": "hello"})
        alerts = [row for row in store.read_records() if row.kind == "alert"]
    assert alerts == []


def test_new_value_class_alerts_once_warm(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    with BaselineStore(db) as store:
        aid = store.append_artefact("mcp_server", "demo", "dashboard")
        _fill(store, aid, WARMUP, {"body": "hello"})
        record_observation(
            store.path,
            server_id="demo",
            tool="send_email",
            arguments={"body": "10.1.1.1"},
            result_size=20,
            outcome="ok",
        )
        reasons = score_latest(store, artefact_id=aid, server_id="demo", tool="send_email", ts=TS)
        alerts = [row for row in store.read_records() if row.kind == "alert"]
        assert store.verify_chain().ok
    assert reasons == ["value class private_ip"]
    assert len(alerts) == 1
    assert "private_ip" in alerts[0].payload
    assert "Input now includes private_ip" in alerts[0].payload
