"""SQLite WAL baseline store. Append-only API; historical rows are never rewritten (T-06)."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

from cim.common.chain import GENESIS_HASH, compute_record_hash
from cim.common.schema.canonical import canonical_json

_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
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
class ChainStatus:
    """Result of recomputing the hash chain from stored rows."""

    ok: bool
    count: int
    broken_at: int | None
    reason: str


class BaselineStore:
    """Append-only artefact and event log with a hash-chained record table."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._depth = 0
        self._tip: str | None = None
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
        """Group several appends into one commit. Still append-only."""
        self._depth += 1
        try:
            yield
        except Exception:
            self._conn.rollback()
            self._tip = None
            raise
        else:
            if self._depth == 1:
                self._conn.commit()
        finally:
            self._depth -= 1

    def append_artefact(self, artefact_type: str, name: str, origin: str) -> int:
        """Insert one artefact row and return its id."""
        if not artefact_type or not name or not origin:
            raise ValueError("artefact type, name, and origin must be non-empty")
        cursor = self._conn.execute(
            "INSERT INTO artefact (type, name, origin) VALUES (?, ?, ?)",
            (artefact_type, name, origin),
        )
        self._commit_if_needed()
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not assign an artefact id")
        return int(cursor.lastrowid)

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
        if (
            self._conn.execute(
                "SELECT 1 FROM artefact WHERE id = ?",
                (artefact_id,),
            ).fetchone()
            is None
        ):
            raise ValueError(f"unknown artefact id: {artefact_id}")
        encoded = canonical_json(payload)
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
        self._commit_if_needed()
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
                )
            expected = compute_record_hash(prev, kind, payload)
            if stored_hash != expected:
                return ChainStatus(
                    ok=False,
                    count=len(rows),
                    broken_at=record_id,
                    reason="record_hash does not match the stored payload",
                )
            prev = stored_hash
            expected_id += 1
        return ChainStatus(ok=True, count=len(rows), broken_at=None, reason="ok")

    def _tip_hash(self) -> str:
        if self._tip is None:
            row = self._conn.execute(
                "SELECT record_hash FROM record ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self._tip = GENESIS_HASH if row is None else str(row["record_hash"])
        return self._tip

    def _commit_if_needed(self) -> None:
        if self._depth == 0:
            self._conn.commit()
