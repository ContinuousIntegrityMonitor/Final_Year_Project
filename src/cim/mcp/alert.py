"""Behaviour alert for one MCP tool (T-16, MCP half).

The first 30 calls of a tool are warm-up and never alert. After that, the newest
call is compared with the calls already seen. An alert names what is new:
a value class, an argument shape, the first error, or a much larger result.
Scores are integers. Nothing here is a float, and nothing is refused.

Observations come from hash-chained ``behaviour`` records (contract 1.1 fields).
The off-chain ``envelope_obs`` table is not read: wiping it cannot silence an alert
while ``verify-chain`` still passes (test report M1). Shared ``common/scorer.py``
will replace these fixed rules when Fasih lands it; this module only switches the
input source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from cim.common.store import BaselineStore
from cim.mcp.envelope import WARMUP, WINDOW

_CODE = "mcp_behaviour_drift"


@dataclass(frozen=True)
class _Obs:
    """One scorable MCP call, taken from a chained behaviour payload."""

    argument_shape: str  # argument_shape_digest
    value_classes: tuple[str, ...]
    result_size: int  # response_bytes
    outcome: str


def score_latest(
    store: BaselineStore,
    *,
    artefact_id: int,
    server_id: str,
    tool: str,
    ts: str,
) -> list[str]:
    """Alert when the newest call leaves the pattern learned so far. Empty means no alert."""
    rows = _observations(store, server_id, tool)
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


def _observations(store: BaselineStore, server_id: str, tool: str) -> list[_Obs]:
    """Scorable behaviour rows for one tool, in chain order. Skips pre-1.1 payloads."""
    found: list[_Obs] = []
    for row in store.read_records():
        if row.kind != "behaviour":
            continue
        try:
            payload: dict[str, Any] = json.loads(row.payload)
        except json.JSONDecodeError:
            continue
        if payload.get("server_id") != server_id or payload.get("tool_id") != tool:
            continue
        digest = payload.get("argument_shape_digest")
        classes = payload.get("value_classes")
        size = payload.get("response_bytes")
        outcome = payload.get("outcome")
        if not isinstance(digest, str) or not digest:
            continue
        if not isinstance(classes, list):
            continue
        if not isinstance(size, int) or isinstance(size, bool):
            continue
        if not isinstance(outcome, str) or not outcome:
            continue
        found.append(
            _Obs(
                argument_shape=digest,
                value_classes=tuple(str(item) for item in classes),
                result_size=size,
                outcome=outcome,
            )
        )
    return found


def _reasons(prior: list[_Obs], latest: _Obs) -> list[str]:
    classes: set[str] = set()
    shapes: set[str] = set()
    sizes: list[int] = []
    for row in prior:
        classes.update(row.value_classes)
        shapes.add(row.argument_shape)
        sizes.append(row.result_size)
    found: list[str] = []
    fresh = sorted(set(latest.value_classes) - classes)
    if fresh:
        found.append("value class " + ", ".join(fresh))
    if latest.argument_shape not in shapes:
        found.append("argument shape")
    if latest.outcome != "ok" and all(row.outcome == "ok" for row in prior):
        found.append("first error")
    sizes.sort()
    median = sizes[len(sizes) // 2]
    newest = latest.result_size
    if median > 0 and newest >= median * 3 and newest > median + 50:
        found.append("result size")
    return found


def _plain_changes(prior: list[_Obs], latest: _Obs) -> tuple[str, str]:
    """Say what moved in the input and in the output, in plain words."""
    classes: set[str] = set()
    shapes: set[str] = set()
    sizes: list[int] = []
    for row in prior:
        classes.update(row.value_classes)
        shapes.add(row.argument_shape)
        sizes.append(row.result_size)
    fresh = sorted(set(latest.value_classes) - classes)
    input_parts: list[str] = []
    if fresh:
        input_parts.append(
            "Input now includes " + ", ".join(fresh) + ", which earlier calls did not."
        )
    if latest.argument_shape not in shapes:
        input_parts.append("Input shape is different from earlier calls.")
    if not input_parts:
        input_parts.append("Input matches the calls seen so far.")
    sizes.sort()
    median = sizes[len(sizes) // 2]
    newest = latest.result_size
    output_parts: list[str] = []
    if latest.outcome != "ok" and all(row.outcome == "ok" for row in prior):
        output_parts.append("Output failed. Earlier calls succeeded.")
    if median > 0 and newest >= median * 3 and newest > median + 50:
        output_parts.append(f"Output grew from about {median} to {newest}.")
    if not output_parts:
        output_parts.append("Output size and result match earlier calls.")
    return " ".join(input_parts), " ".join(output_parts)
