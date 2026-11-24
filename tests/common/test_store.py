"""Append-only baseline store and verify-chain (T-06)."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cim.cli import app
from cim.common.chain import GENESIS_HASH, HASH_V1, HASH_V2, compute_record_hash_v1
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


# ---- several writers on one store


def test_two_handles_appending_in_turn_keep_the_chain_whole(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    with BaselineStore(path) as first, BaselineStore(path) as second:
        artefact_id = first.append_artefact("skill", "pdf-tools", "lab")
        first.append_record(artefact_id, "integrity", {"n": 1}, TS)
        second.append_record(artefact_id, "integrity", {"n": 2}, TS)
        first.append_record(artefact_id, "integrity", {"n": 3}, TS)  # must chain from record 2
        with second.transaction():
            second.append_record(artefact_id, "integrity", {"n": 4}, TS)
            second.append_record(artefact_id, "integrity", {"n": 5}, TS)
        first.append_record(artefact_id, "integrity", {"n": 6}, TS)
        status = first.verify_chain()
    assert status.ok, status
    assert status.count == 6


_WRITER = """
import sys
from cim.common.store import BaselineStore
path, name, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
with BaselineStore(path) as store:
    artefact_id = store.get_or_create_artefact("skill", "shared", "lab")
    for n in range(count):
        payload = {"writer": name, "n": n}
        store.append_record(artefact_id, "behaviour", payload, "2026-10-19T12:00:00Z")
"""


def test_four_processes_writing_at_once_keep_the_chain_whole(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    with BaselineStore(path):
        pass  # create the file before the writers race to
    writers = [
        subprocess.Popen([sys.executable, "-c", _WRITER, str(path), f"w{i}", "150"])
        for i in range(4)
    ]
    assert [writer.wait(timeout=120) for writer in writers] == [0, 0, 0, 0]
    with BaselineStore(path) as store:
        status = store.verify_chain()
        artefacts = {record.artefact_id for record in store.read_records()}
    assert status.ok, status
    assert status.count == 600
    assert len(artefacts) == 1  # the four writers found each other's artefact row


def test_failed_transaction_leaves_nothing_behind(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        artefact_id = store.append_artefact("skill", "pdf-tools", "lab")
        store.append_record(artefact_id, "integrity", {"n": 1}, TS)
        with pytest.raises(ValueError, match="floats"), store.transaction():
            store.append_record(artefact_id, "integrity", {"n": 2}, TS)
            with store.transaction():  # nested blocks join the outer one
                store.append_record(artefact_id, "integrity", {"n": 3}, TS)
            store.append_record(artefact_id, "integrity", {"bad": 1.5}, TS)
        store.append_record(artefact_id, "integrity", {"n": 4}, TS)
        status = store.verify_chain()
        payloads = [record.payload for record in store.read_records()]
    assert status.ok
    assert payloads == ['{"n":1}', '{"n":4}']


def test_writer_waits_for_the_lock_instead_of_failing(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    with BaselineStore(path) as holder:
        artefact_id = holder.append_artefact("skill", "pdf-tools", "lab")
        waiter = subprocess.Popen([sys.executable, "-c", _WRITER, str(path), "late", "1"])
        with holder.transaction():
            holder.append_record(artefact_id, "integrity", {"n": 1}, TS)
            time.sleep(1.0)  # the other process is blocked for this long
            assert waiter.poll() is None
        assert waiter.wait(timeout=60) == 0
        status = holder.verify_chain()
    assert status.ok
    assert status.count == 2


# ---- artefact look-up


def test_get_or_create_artefact_reuses_the_row(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        assert store.find_artefact("mcp_tool", "nmap_scan", "vm-mon") is None
        first = store.get_or_create_artefact("mcp_tool", "nmap_scan", "vm-mon")
        assert store.get_or_create_artefact("mcp_tool", "nmap_scan", "vm-mon") == first
        assert store.find_artefact("mcp_tool", "nmap_scan", "vm-mon") == first
        # A different type, name or origin is a different artefact.
        others = {
            store.get_or_create_artefact("mcp_server", "nmap_scan", "vm-mon"),
            store.get_or_create_artefact("mcp_tool", "other", "vm-mon"),
            store.get_or_create_artefact("mcp_tool", "nmap_scan", "laptop"),
        }
        assert len(others | {first}) == 4
    with _store(tmp_path) as reopened:  # and it survives a restart
        assert reopened.get_or_create_artefact("mcp_tool", "nmap_scan", "vm-mon") == first


# ---- timestamps


@pytest.mark.parametrize(
    "ts", ["2026-13-01T00:00:00Z", "2026-02-30T00:00:00Z", "2026-01-01T99:99:99Z"]
)
def test_impossible_timestamp_rejected(tmp_path: Path, ts: str) -> None:
    with _store(tmp_path) as store:
        artefact_id = store.append_artefact("skill", "pdf-tools", "lab")
        with pytest.raises(ValueError, match="not a real date"):
            store.append_record(artefact_id, "integrity", {"n": 1}, ts)
        assert store.verify_chain().count == 0


# ---- tip and count


def test_chain_status_carries_the_tip(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    with BaselineStore(path) as store:
        assert store.verify_chain().tip == GENESIS_HASH
        artefact_id = store.append_artefact("skill", "pdf-tools", "lab")
        for n in (1, 2, 3):
            store.append_record(artefact_id, "integrity", {"n": n}, TS)
        whole = store.verify_chain()
    raw = sqlite3.connect(path)
    hashes = [row[0] for row in raw.execute("SELECT record_hash FROM record ORDER BY id")]
    raw.execute("UPDATE record SET payload = ? WHERE id = 3", ('{"n":9}',))
    raw.commit()
    raw.close()
    assert whole.tip == hashes[2]
    with BaselineStore(path) as store:
        broken = store.verify_chain()
    assert not broken.ok
    assert broken.tip == hashes[1]  # the last record that still verified


def test_new_store_is_hash_v2(tmp_path: Path) -> None:
    with _store(tmp_path) as store:
        assert store.hash_version == HASH_V2
        artefact_id = store.append_artefact("skill", "pdf-tools", "lab")
        store.append_record(artefact_id, "behaviour", {"n": 1}, TS)
        status = store.verify_chain()
    assert status.ok
    assert status.hash_version == HASH_V2
    assert status.reason == "ok"


def _two_behaviour_records(path: Path) -> tuple[int, int]:
    with BaselineStore(path) as store:
        tool_a = store.append_artefact("mcp_tool", "shout", "lab")
        tool_b = store.append_artefact("mcp_tool", "add", "lab")
        store.append_record(tool_a, "behaviour", {"n": 1}, TS)
        store.append_record(tool_a, "behaviour", {"n": 2}, TS)
        assert store.verify_chain().ok
    return tool_a, tool_b


def test_redate_breaks_v2_chain(tmp_path: Path) -> None:
    path = tmp_path / "redate.db"
    _two_behaviour_records(path)
    raw = sqlite3.connect(path)
    raw.execute("UPDATE record SET ts = '1999-01-01T00:00:00Z' WHERE id = 1")
    raw.commit()
    raw.close()
    with BaselineStore(path) as store:
        status = store.verify_chain()
    assert not status.ok
    assert status.broken_at == 1


def test_move_breaks_v2_chain(tmp_path: Path) -> None:
    path = tmp_path / "move.db"
    _tool_a, tool_b = _two_behaviour_records(path)
    raw = sqlite3.connect(path)
    raw.execute("UPDATE record SET artefact_id = ? WHERE id = 1", (tool_b,))
    raw.commit()
    raw.close()
    with BaselineStore(path) as store:
        status = store.verify_chain()
    assert not status.ok
    assert status.broken_at == 1


def test_rename_artefact_breaks_v2_chain(tmp_path: Path) -> None:
    path = tmp_path / "rename.db"
    tool_a, _tool_b = _two_behaviour_records(path)
    with BaselineStore(path) as store:
        tip_before = store.verify_chain().tip
    raw = sqlite3.connect(path)
    raw.execute(
        "UPDATE artefact SET name = 'not-shout', origin = 'elsewhere' WHERE id = ?",
        (tool_a,),
    )
    raw.commit()
    raw.close()
    with BaselineStore(path) as store:
        status = store.verify_chain()
    assert not status.ok
    assert status.broken_at == 1
    assert status.tip != tip_before


def test_v1_store_verifies_but_refuses_append(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    # Build a v1 chain with the old formula and no store_meta.hash_version.
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE artefact (
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            origin TEXT NOT NULL
        );
        CREATE TABLE record (
            id INTEGER PRIMARY KEY,
            artefact_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            payload TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            record_hash TEXT NOT NULL,
            ts TEXT NOT NULL
        );
        """
    )
    con.execute("INSERT INTO artefact (type, name, origin) VALUES ('skill', 'pdf-tools', 'lab')")
    payload = '{"n":1}'
    digest = compute_record_hash_v1(GENESIS_HASH, "behaviour", payload)
    con.execute(
        """
        INSERT INTO record (artefact_id, kind, payload, prev_hash, record_hash, ts)
        VALUES (1, 'behaviour', ?, ?, ?, ?)
        """,
        (payload, GENESIS_HASH, digest, TS),
    )
    con.commit()
    con.close()

    with BaselineStore(path) as store:
        assert store.hash_version == HASH_V1
        status = store.verify_chain()
        assert status.ok
        assert status.hash_version == HASH_V1
        assert "hash v1" in status.reason
        with pytest.raises(ValueError, match="hash v1"):
            store.append_record(1, "behaviour", {"n": 2}, TS)

    cli = runner.invoke(app, ["verify-chain", "--db", str(path)])
    assert cli.exit_code == 0
    assert "hash v1: ts and artefacts not covered" in cli.stdout


def test_cli_catches_a_chain_that_was_cut_short(tmp_path: Path) -> None:
    path = tmp_path / "baseline.db"
    with BaselineStore(path) as store:
        artefact_id = store.append_artefact("skill", "pdf-tools", "lab")
        for n in (1, 2, 3):
            store.append_record(artefact_id, "integrity", {"n": n}, TS)
        tip = store.verify_chain().tip
    args = ["verify-chain", "--db", str(path)]
    ok = runner.invoke(app, [*args, "--expect-tip", tip.upper(), "--min-count", "3"])
    assert ok.exit_code == 0
    assert f"ok (3 records) tip={tip}" in ok.stdout
    raw = sqlite3.connect(path)
    raw.execute("DELETE FROM record WHERE id = 3")
    raw.commit()
    raw.close()
    assert runner.invoke(app, args).exit_code == 0  # a shorter chain still verifies on its own
    short = runner.invoke(app, [*args, "--min-count", "3"])
    assert short.exit_code == 1
    assert "records are missing: 2 found, 3 expected" in short.stdout
    moved = runner.invoke(app, [*args, "--expect-tip", tip])
    assert moved.exit_code == 1
    assert "not the expected" in moved.stdout
