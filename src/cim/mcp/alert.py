"""Behaviour alert for one MCP tool (T-16, MCP half).

Observations come from hash-chained ``behaviour`` records (contract 1.1 fields).
Scoring uses ``cim.common.scorer`` (integer milli-z). Alerted runs stay out of the
baseline window (A1). The off-chain ``envelope_obs`` table is never read.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from cim.common.schema.alerts import BehaviourAlertPayload, DriftFeature
from cim.common.scorer import (
    SCORER_VERSION,
    FeatureRule,
    Observation,
    ScorerConfig,
    baseline,
    score,
)
from cim.common.store import BaselineStore
from cim.mcp.envelope import WARMUP, WINDOW
from cim.mcp.events import append_mcp

_CODE: Literal["mcp_behaviour_drift"] = "mcp_behaviour_drift"

MCP_SCORER = ScorerConfig(
    rules={
        "argument_shape": FeatureRule(kind="categorical"),
        "value_class": FeatureRule(kind="categorical"),
        "outcome": FeatureRule(kind="categorical"),
        "result_size": FeatureRule(kind="numeric", threshold_milli=4000, floor_ratio=10),
    },
    window=WINDOW,
    warmup=WARMUP,
)


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
    if not rows:
        return []
    alerted_ids = _alerted_observation_ids(store, server_id, tool)
    history = [(obs, record_id in alerted_ids) for record_id, obs in rows]
    latest_id, latest_obs = rows[-1]
    prior = baseline(history[:-1], MCP_SCORER)
    result = score(prior, latest_obs, MCP_SCORER)
    if not result.alert:
        return []
    reasons = _reason_strings(result.drifted)
    input_change, output_change = _plain_changes(result.drifted, latest_obs)
    detail = f"{tool} changed how it is used: " + "; ".join(reasons)
    features = [
        DriftFeature(
            feature=item.feature,
            how=item.how,
            values=list(item.values),
            score_milli=item.score_milli,
            threshold_milli=item.threshold_milli,
        )
        for item in result.drifted
    ]
    payload = BehaviourAlertPayload(
        code=_CODE,
        server_id=server_id,
        tool_id=tool,
        observation_record_id=latest_id,
        composite_milli=result.composite_milli,
        features=features,
        window=MCP_SCORER.window,
        scorer_version=SCORER_VERSION,
        detail=detail,
        input_change=input_change,
        output_change=output_change,
    )
    append_mcp(
        store,
        artefact_id,
        artefact_type="mcp_server",
        server_id=server_id,
        kind="alert",
        payload=payload,
        ts=ts,
    )
    return reasons


def _observations(store: BaselineStore, server_id: str, tool: str) -> list[tuple[int, Observation]]:
    """Scorable behaviour rows for one tool, in chain order. Skips pre-1.1 payloads."""
    found: list[tuple[int, Observation]] = []
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
        obs = Observation(
            categorical={
                "argument_shape": frozenset({digest}),
                "value_class": frozenset(str(item) for item in classes),
                "outcome": frozenset({outcome}),
            },
            numeric={"result_size": size},
        )
        found.append((row.id, obs))
    return found


def _alerted_observation_ids(store: BaselineStore, server_id: str, tool: str) -> set[int]:
    """Behaviour record ids that already raised ``mcp_behaviour_drift`` for this tool."""
    found: set[int] = set()
    for row in store.read_records():
        if row.kind != "alert":
            continue
        try:
            payload: dict[str, Any] = json.loads(row.payload)
        except json.JSONDecodeError:
            continue
        if payload.get("code") != _CODE:
            continue
        if payload.get("server_id") != server_id or payload.get("tool_id") != tool:
            continue
        oid = payload.get("observation_record_id")
        if isinstance(oid, int) and not isinstance(oid, bool):
            found.add(oid)
    return found


def _reason_strings(drifts: tuple[Any, ...]) -> list[str]:
    """Stable short reasons for tests and detail text."""
    found: list[str] = []
    for item in drifts:
        if item.feature == "value_class" and item.how == "never_seen":
            found.append("value class " + ", ".join(item.values))
        elif item.feature == "argument_shape":
            found.append("argument shape")
        elif item.feature == "outcome":
            found.append("first error")
        elif item.feature == "result_size":
            found.append("result size")
        else:
            found.append(f"{item.feature} {item.how}")
    return found


def _plain_changes(drifts: tuple[Any, ...], latest: Observation) -> tuple[str, str]:
    """Say what moved in the input and in the output, in plain words."""
    features = {item.feature for item in drifts}
    input_parts: list[str] = []
    output_parts: list[str] = []
    for item in drifts:
        if item.feature == "value_class" and item.how == "never_seen":
            input_parts.append(
                "Input now includes " + ", ".join(item.values) + ", which earlier calls did not."
            )
        elif item.feature == "argument_shape":
            input_parts.append("Input shape is different from earlier calls.")
        elif item.feature == "outcome":
            output_parts.append("Output failed. Earlier calls succeeded.")
        elif item.feature == "result_size":
            size = latest.numeric.get("result_size", 0)
            output_parts.append(f"Output grew to {size}.")
    if not input_parts:
        input_parts.append("Input matches the calls seen so far.")
    if not output_parts:
        output_parts.append("Output size and result match earlier calls.")
    _ = features  # kept for clarity when extending
    return " ".join(input_parts), " ".join(output_parts)
