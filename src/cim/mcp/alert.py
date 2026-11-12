"""Behaviour alert for one MCP tool (T-16, MCP half).

The first 30 calls of a tool are warm-up and never alert. After that, the newest
call is compared with the calls already seen. An alert names what is new:
a value class, an argument shape, the first error, or a much larger result.
Scores are integers. Nothing here is a float, and nothing is refused.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from cim.common.store import BaselineStore
from cim.mcp.envelope import WARMUP, WINDOW, json_list

_CODE = "mcp_behaviour_drift"


def score_latest(
    store: BaselineStore,
    *,
    artefact_id: int,
    server_id: str,
    tool: str,
    ts: str,
) -> list[str]:
    """Alert when the newest call leaves the pattern learned so far. Empty means no alert."""
    rows = _rows(store.path, server_id, tool)
    if len(rows) <= WARMUP:
        return []
    prior = rows[-(WINDOW + 1) : -1]
    if len(prior) < WARMUP:
        return []
    reasons = _reasons(prior, rows[-1])[:3]
    if not reasons:
        return []
    input_change, output_change = _plain_changes(prior, rows[-1])
    detail = f"{tool} changed how it is used: " + "; ".join(reasons)
    store.append_record(
        artefact_id,
        "alert",
        {
            "code": _CODE,
            "server_id": server_id,
            "tool_id": tool,
            "detail": detail,
            "features": reasons,
            "input_change": input_change,
            "output_change": output_change,
        },
        ts,
    )
    return reasons


def _rows(db: Any, server_id: str, tool: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        found = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'envelope_obs'"
        ).fetchone()
        if found is None:
            return []
        return list(
            conn.execute(
                """
                SELECT argument_shape, value_classes, result_size, outcome
                FROM envelope_obs
                WHERE server_id = ? AND tool_id = ?
                ORDER BY id
                """,
                (server_id, tool),
            ).fetchall()
        )
    finally:
        conn.close()


def _reasons(prior: list[sqlite3.Row], latest: sqlite3.Row) -> list[str]:
    classes: set[str] = set()
    shapes: set[str] = set()
    sizes: list[int] = []
    for row in prior:
        classes.update(json_list(str(row["value_classes"])))
        shapes.add(str(row["argument_shape"]))
        sizes.append(int(row["result_size"]))
    found: list[str] = []
    fresh = sorted(set(json_list(str(latest["value_classes"]))) - classes)
    if fresh:
        found.append("value class " + ", ".join(fresh))
    if str(latest["argument_shape"]) not in shapes:
        found.append("argument shape")
    if str(latest["outcome"]) != "ok" and all(str(row["outcome"]) == "ok" for row in prior):
        found.append("first error")
    sizes.sort()
    median = sizes[len(sizes) // 2]
    newest = int(latest["result_size"])
    if median > 0 and newest >= median * 3 and newest > median + 50:
        found.append("result size")
    return found


def _plain_changes(prior: list[sqlite3.Row], latest: sqlite3.Row) -> tuple[str, str]:
    """Say what moved in the input and in the output, in plain words."""
    classes: set[str] = set()
    shapes: set[str] = set()
    sizes: list[int] = []
    for row in prior:
        classes.update(json_list(str(row["value_classes"])))
        shapes.add(str(row["argument_shape"]))
        sizes.append(int(row["result_size"]))
    fresh = sorted(set(json_list(str(latest["value_classes"]))) - classes)
    input_parts: list[str] = []
    if fresh:
        input_parts.append(
            "Input now includes " + ", ".join(fresh) + ", which earlier calls did not."
        )
    if str(latest["argument_shape"]) not in shapes:
        input_parts.append("Input shape is different from earlier calls.")
    if not input_parts:
        input_parts.append("Input matches the calls seen so far.")
    sizes.sort()
    median = sizes[len(sizes) // 2]
    newest = int(latest["result_size"])
    output_parts: list[str] = []
    if str(latest["outcome"]) != "ok" and all(str(row["outcome"]) == "ok" for row in prior):
        output_parts.append("Output failed. Earlier calls succeeded.")
    if median > 0 and newest >= median * 3 and newest > median + 50:
        output_parts.append(f"Output grew from about {median} to {newest}.")
    if not output_parts:
        output_parts.append("Output size and result match earlier calls.")
    return " ".join(input_parts), " ".join(output_parts)
