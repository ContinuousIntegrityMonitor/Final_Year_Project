"""Append-only baseline store and verify-chain (T-06)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cim.cli import app
from cim.common.store import BaselineStore
from cim.common.store.baseline import _DDL

runner = CliRunner()
TS = "2026-10-19T12:00:00Z"


def _store(tmp_path: Path) -> BaselineStore:
    return BaselineStore(tmp_path / "baseline.db")


def test_append_and_verify_round_trip(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        artefact_id = store.append_artefact("skill", "pdf-tools", "lab")
        record_id = store.append_record(
            artefact_id,
            "behaviour",
            {"skill_id": "pdf-tools", "ok": True},
            TS,
        )
        status = store.verify_chain()
    assert artefact_id == 1
    assert record_id == 1
    assert status.ok
    assert status.count == 1


def test_float_payload_rejected(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        artefact_id = store.append_artefact("mcp_tool", "nmap_scan", "hexstrike")
        with pytest.raises(ValueError, match="floats"):
            store.append_record(artefact_id, "behaviour", {"n": 1.5}, TS)


def test_no_update_or_delete_api(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert not hasattr(store, "update_record")
    assert not hasattr(store, "delete_record")
    assert not hasattr(store, "update_artefact")
    sql = "\n".join(_DDL).upper()
    assert "UPDATE " not in sql
    assert "DELETE " not in sql
    store.close()


def test_edited_historical_row_breaks_chain(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    with BaselineStore(path) as store:
        artefact_id = store.append_artefact("skill", "pdf-tools", "lab")
        store.append_record(artefact_id, "behaviour", {"n": 1}, TS)
        store.append_record(artefact_id, "behaviour", {"n": 2}, TS)
    raw = sqlite3.connect(path)
    raw.execute("UPDATE record SET payload = ? WHERE id = 1", ('{"n":9}',))
    raw.commit()
    raw.close()
    with BaselineStore(path) as store:
        status = store.verify_chain()
    assert not status.ok
    assert status.broken_at == 1


def test_deleted_historical_row_breaks_chain(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    with BaselineStore(path) as store:
        artefact_id = store.append_artefact("skill", "pdf-tools", "lab")
        for n in (1, 2, 3):
            store.append_record(artefact_id, "integrity", {"n": n}, TS)
    raw = sqlite3.connect(path)
    raw.execute("DELETE FROM record WHERE id = 2")
    raw.commit()
    raw.close()
    with BaselineStore(path) as store:
        status = store.verify_chain()
    assert not status.ok
    assert status.broken_at == 3


def test_ten_thousand_appends_under_five_seconds(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        artefact_id = store.append_artefact("mcp_server", "hexstrike", "vm-mon")
        started = time.perf_counter()
        with store.transaction():
            for n in range(10_000):
                store.append_record(artefact_id, "behaviour", {"n": n}, TS)
        elapsed = time.perf_counter() - started
        status = store.verify_chain()
    assert elapsed < 5.0
    assert status.ok
    assert status.count == 10_000


def test_verify_chain_cli_ok_and_broken(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    with BaselineStore(path) as store:
        artefact_id = store.append_artefact("skill", "pdf-tools", "lab")
        store.append_record(artefact_id, "alert", {"code": "ok"}, TS)
    ok = runner.invoke(app, ["verify-chain", "--db", str(path)])
    assert ok.exit_code == 0
    assert "ok (1 records)" in ok.stdout
    raw = sqlite3.connect(path)
    raw.execute("UPDATE record SET kind = 'behaviour' WHERE id = 1")
    raw.commit()
    raw.close()
    broken = runner.invoke(app, ["verify-chain", "--db", str(path)])
    assert broken.exit_code == 1
    assert "broken" in broken.stdout
