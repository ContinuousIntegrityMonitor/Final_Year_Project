"""SQLite WAL baseline store. Append-only API; historical rows are never rewritten (T-06).

Several processes may append to one store (the MCP proxy, the skills watcher, a CLI sweep).
Every append therefore runs inside a write transaction that is opened with BEGIN IMMEDIATE,
and the chain tip is read inside that transaction. A second writer waits its turn instead of
chaining from a tip that is no longer the last record.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from cim.common.chain import GENESIS_HASH, compute_record_hash
from cim.common.schema.canonical import canonical_json

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
BUSY_TIMEOUT_S = 30.0  # how long one writer waits for another before giving up
_KINDS = frozenset({"artefact", "integrity", "behaviour", "alert"})

_DDL = (
    """
    CREATE TABLE IF NOT EXISTS artefact (
        id INTEGER PRIMARY KEY,
        type TEXT NOT NULL,
        name TEXT NOT NULL,
        origin TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS record (
        id INTEGER PRIMARY KEY,
        artefact_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        payload TEXT NOT NULL,
        prev_hash TEXT NOT NULL,
        record_hash TEXT NOT NULL,
        ts TEXT NOT NULL
    )
    """,
)


@dataclass(frozen=True)
class StoredRecord:
    """One row of the log, in chain order. Read-only view; rows are never updated."""

    id: int
    artefact_id: int
    kind: str
    payload: str
    ts: str


@dataclass(frozen=True)
class ChainStatus:
    """Result of recomputing the hash chain from stored rows."""

    ok: bool
    count: int
    broken_at: int | None
    reason: str
    tip: str = GENESIS_HASH  # hash of the last record that verified; genesis if none did


class BaselineStore:
    """Append-only artefact and event log with a hash-chained record table."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        # isolation_level=None: transactions are opened and closed here, explicitly, so that
        # reading the tip and inserting the next record are one locked step.
        self._conn = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_S, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._tip: str | None = None  # only trusted while this handle holds the write lock
        mode = self._conn.execute("PRAGMA journal_mode=WAL").fetchone()
        if mode is None or str(mode[0]).lower() != "wal":
            raise RuntimeError("SQLite refused WAL mode")
        for statement in _DDL:
            self._conn.execute(statement)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group several appends into one commit. Still append-only.

        The write lock is held for the whole block, so other writers wait until it ends.
        Nested blocks join the outer one. An exception rolls everything in the block back.
        """
        if self._conn.in_transaction:
            yield  # joined: the outermost block commits or rolls back
            return
        self._conn.execute("BEGIN IMMEDIATE")
        self._tip = None
        try:
            yield
        except BaseException:
            self._conn.rollback()
            raise
        else:
            self._conn.commit()
        finally:
            self._tip = None

    def append_artefact(self, artefact_type: str, name: str, origin: str) -> int:
        """Insert one artefact row and return its id."""
        if not artefact_type or not name or not origin:
            raise ValueError("artefact type, name, and origin must be non-empty")
        with self.transaction():
            cursor = self._conn.execute(
                "INSERT INTO artefact (type, name, origin) VALUES (?, ?, ?)",
                (artefact_type, name, origin),
            )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not assign an artefact id")
        return int(cursor.lastrowid)

    def find_artefact(self, artefact_type: str, name: str, origin: str) -> int | None:
        """Id of the first artefact row with this type, name and origin, or None."""
        row = self._conn.execute(
            """
            SELECT id FROM artefact
            WHERE type = ? AND name = ? AND origin = ? ORDER BY id LIMIT 1
            """,
            (artefact_type, name, origin),
        ).fetchone()
        return None if row is None else int(row["id"])

    def get_or_create_artefact(self, artefact_type: str, name: str, origin: str) -> int:
        """Return the existing artefact row for this type, name and origin, or insert one.

        Lets a collector that restarts keep writing under the same artefact instead of
        adding a new row per session. Nothing existing is changed.
        """
        with self.transaction():  # look-up and insert are one locked step
            found = self.find_artefact(artefact_type, name, origin)
            if found is not None:
                return found
            return self.append_artefact(artefact_type, name, origin)

    def append_record(
        self,
        artefact_id: int,
        kind: str,
        payload: dict[str, Any],
        ts: str,
    ) -> int:
        """Append one hash-chained record. Payload is stored as canonical JSON."""
        if kind not in _KINDS:
            raise ValueError(f"unknown record kind: {kind}")
        if _TS.fullmatch(ts) is None:
            raise ValueError(f"timestamp must be UTC Zulu seconds: {ts}")
        try:
            datetime.strptime(ts, _TS_FORMAT)
        except ValueError:
            raise ValueError(f"timestamp is not a real date and time: {ts}") from None
        encoded = canonical_json(payload)
        with self.transaction():
            known = self._conn.execute(
                "SELECT 1 FROM artefact WHERE id = ?", (artefact_id,)
            ).fetchone()
            if known is None:
                raise ValueError(f"unknown artefact id: {artefact_id}")
            prev_hash = self._tip_hash()
            record_hash = compute_record_hash(prev_hash, kind, encoded)
            cursor = self._conn.execute(
                """
                INSERT INTO record (artefact_id, kind, payload, prev_hash, record_hash, ts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (artefact_id, kind, encoded, prev_hash, record_hash, ts),
            )
            self._tip = record_hash
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not assign a record id")
        return int(cursor.lastrowid)

    def verify_chain(self) -> ChainStatus:
        """Recompute every record hash. An edited or deleted historical row fails."""
        rows = self._conn.execute(
            "SELECT id, kind, payload, prev_hash, record_hash FROM record ORDER BY id"
        ).fetchall()
        prev = GENESIS_HASH
        expected_id = 1
        for row in rows:
            record_id = int(row["id"])
            if record_id != expected_id:
                return ChainStatus(
                    ok=False,
                    count=len(rows),
                    broken_at=record_id,
                    reason=f"missing record id {expected_id}",
                    tip=prev,
                )
            kind = str(row["kind"])
            payload = str(row["payload"])
            stored_prev = str(row["prev_hash"])
            stored_hash = str(row["record_hash"])
            if stored_prev != prev:
                return ChainStatus(
                    ok=False,
                    count=len(rows),
                    broken_at=record_id,
                    reason="prev_hash does not match the previous record",
                    tip=prev,
                )
            expected = compute_record_hash(prev, kind, payload)
            if stored_hash != expected:
                return ChainStatus(
                    ok=False,
                    count=len(rows),
                    broken_at=record_id,
                    reason="record_hash does not match the stored payload",
                    tip=prev,
                )
            prev = stored_hash
            expected_id += 1
        return ChainStatus(ok=True, count=len(rows), broken_at=None, reason="ok", tip=prev)

    def read_records(self) -> list[StoredRecord]:
        """Return every record in chain order. Does not modify the store."""
        rows = self._conn.execute(
            "SELECT id, artefact_id, kind, payload, ts FROM record ORDER BY id"
        ).fetchall()
        return [
            StoredRecord(
                id=int(row["id"]),
                artefact_id=int(row["artefact_id"]),
                kind=str(row["kind"]),
                payload=str(row["payload"]),
                ts=str(row["ts"]),
            )
            for row in rows
        ]

    def _tip_hash(self) -> str:
        """Hash of the last record. Call only while holding the write lock."""
        if self._tip is None:
            row = self._conn.execute(
                "SELECT record_hash FROM record ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self._tip = GENESIS_HASH if row is None else str(row["record_hash"])
        return self._tip
