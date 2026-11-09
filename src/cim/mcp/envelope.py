"""Per-tool behavioural envelope (T-14).

Features over the last 100 calls of a tool: call count, error count, argument
shape signatures, value classes, and median result size. Counts are integers
(hashed payloads cannot hold floats). Scoring waits until warm-up (30 calls);
this module only extracts features and reports whether the tool is warmed up.
The drift scorer (T-16) consumes these features later.
"""

from __future__ import annotations

import ipaddress
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cim.common.schema.canonical import canonical_json

WINDOW = 100
WARMUP = 30

_DDL = """
CREATE TABLE IF NOT EXISTS envelope_obs (
    id INTEGER PRIMARY KEY,
    server_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    argument_shape TEXT NOT NULL,
    value_classes TEXT NOT NULL,
    result_size INTEGER NOT NULL,
    outcome TEXT NOT NULL
)
"""


def argument_shape(value: Any) -> Any:
    """Replace values by their type so the same shape always serializes the same."""
    if isinstance(value, dict):
        return {str(key): argument_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [argument_shape(value[0])] if value else []
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if value is None:
        return "null"
    return "str"


def value_classes(value: Any) -> list[str]:
    """Classify string leaves: private IP, public IP, domain, path, or other."""
    found: set[str] = set()
    _walk_classes(value, found)
    return sorted(found)


def _walk_classes(value: Any, found: set[str]) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _walk_classes(item, found)
    elif isinstance(value, list):
        for item in value:
            _walk_classes(item, found)
    elif isinstance(value, str):
        found.add(_classify(value))


def _classify(text: str) -> str:
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        ip = None
    if ip is not None:
        return "private_ip" if ip.is_private else "public_ip"
    if text.startswith(("/", "\\")) or (len(text) > 2 and text[1] == ":"):
        return "path"
    if "." in text and " " not in text and "/" not in text:
        return "domain"
    return "other"


@dataclass(frozen=True)
class ToolEnvelope:
    """Features for one tool. Identical observations always yield identical features."""

    tool: str
    observations: int
    warmed_up: bool
    call_count: int
    error_count: int
    shapes: tuple[str, ...]
    value_classes: tuple[str, ...]
    result_size_median: int

    def render(self) -> str:
        state = "warmed_up" if self.warmed_up else f"warming_up {self.observations}/{WARMUP}"
        classes = ",".join(self.value_classes) or "-"
        shapes = ",".join(self.shapes) or "-"
        return (
            f"{self.tool}: {state} window={self.call_count} "
            f"errors={self.error_count}/{self.call_count} "
            f"shapes={shapes} classes={classes} result_size_median={self.result_size_median}"
        )


def _connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute(_DDL)
    conn.commit()
    return conn


def record_observation(
    db: Path,
    *,
    server_id: str,
    tool: str,
    arguments: Any,
    result_size: int,
    outcome: str,
) -> None:
    """Append one call's features. Observations are derived data, not hash-chained evidence."""
    shape = canonical_json(argument_shape(arguments))
    classes = canonical_json(value_classes(arguments))
    with _connect(db) as conn:
        conn.execute(
            """
            INSERT INTO envelope_obs
                (server_id, tool_id, argument_shape, value_classes, result_size, outcome)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (server_id, tool, shape, classes, result_size, outcome),
        )


def envelopes(db: Path, server_id: str, tool: str | None = None) -> list[ToolEnvelope]:
    """Features over the last 100 observations of each tool."""
    with _connect(db) as conn:
        rows = conn.execute(
            """
            SELECT tool_id, argument_shape, value_classes, result_size, outcome
            FROM envelope_obs WHERE server_id = ? ORDER BY id
            """,
            (server_id,),
        ).fetchall()
    by_tool: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        by_tool.setdefault(str(row["tool_id"]), []).append(row)
    names = [tool] if tool is not None else sorted(by_tool)
    return [_features(name, by_tool.get(name, [])[-WINDOW:]) for name in names if name in by_tool]


def _features(tool: str, rows: list[sqlite3.Row]) -> ToolEnvelope:
    sizes = sorted(int(row["result_size"]) for row in rows)
    median = sizes[len(sizes) // 2] if sizes else 0
    classes: set[str] = set()
    for row in rows:
        for item in json_list(str(row["value_classes"])):
            classes.add(item)
    return ToolEnvelope(
        tool=tool,
        observations=len(rows) if len(rows) < WINDOW else WINDOW,
        warmed_up=len(rows) >= WARMUP,
        call_count=len(rows),
        error_count=sum(1 for row in rows if str(row["outcome"]) != "ok"),
        shapes=tuple(sorted({str(row["argument_shape"]) for row in rows})),
        value_classes=tuple(sorted(classes)),
        result_size_median=median,
    )


def json_list(text: str) -> list[str]:
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]
