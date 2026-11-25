"""Behaviour alert for one skill run (T-16, skills half).

`record_behaviour` calls `score_run` right after it appends a run's behaviour record. The run
is scored with the shared scorer (`cim.common.scorer`) against the skill's earlier runs, all
read from hash-chained `behaviour` records (docs/T16_SHARED_SCORER_DESIGN.md, sections 4 to 7):

- categorical: `binaries`, `write_targets`, `destinations` (`dest_class:port`);
- numeric, upward only: `processes`, `binaries_n`, `writes_n`, `destinations_n`.

A run that raised an alert stays out of later windows (A1), so a repeated attack alerts every
time. Which runs alerted is read back from the `skill_behaviour_drift` records themselves,
through `observation_record_id`. The run being scored is named by its record id, never taken
as "the newest record", so two writers to one store cannot score each other's runs.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from cim.common.schema.alerts import BehaviourAlertPayload, DriftFeature
from cim.common.schema.skills import SkillBehaviourPayload
from cim.common.scorer import (
    SCORER_VERSION,
    Drift,
    FeatureRule,
    Observation,
    ScorerConfig,
    baseline,
    score,
)
from cim.common.store import BaselineStore, StoredRecord
from cim.skills.envelope import WARMUP, WINDOW
from cim.skills.inventory import append_event

DRIFT_CODE: Literal["skill_behaviour_drift"] = "skill_behaviour_drift"
FAILED_CODE = "skill_score_failed"

SKILL_SCORER = ScorerConfig(
    rules={
        "binaries": FeatureRule(kind="categorical"),
        "write_targets": FeatureRule(kind="categorical"),
        "destinations": FeatureRule(kind="categorical"),
        "processes": FeatureRule(kind="numeric"),
        "binaries_n": FeatureRule(kind="numeric"),
        "writes_n": FeatureRule(kind="numeric"),
        "destinations_n": FeatureRule(kind="numeric"),
    },
    window=WINDOW,
    warmup=WARMUP,
)


class SkillScoreFailedPayload(BaseModel):
    """Scoring a run failed; the run's behaviour record is stored all the same (test report M4).

    Its code is not in the contract's `ALERT_PAYLOADS`, so the contract checks only `code`;
    this model keeps the record's shape fixed on the skills side.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Literal["skill_score_failed"] = "skill_score_failed"
    reason: Literal["behaviour_score_failed"] = "behaviour_score_failed"
    skill_id: str
    observation_record_id: StrictInt = Field(ge=1)
    detail: str


def observation_of(run: SkillBehaviourPayload) -> Observation:
    """The scorer's view of one run. Counts are of distinct values, as in the profile."""
    binaries = frozenset(run.binaries_executed)
    writes = frozenset(run.file_write_targets)
    destinations = frozenset(f"{e.dest_class}:{e.port}" for e in run.egress)
    return Observation(
        categorical={
            "binaries": binaries,
            "write_targets": writes,
            "destinations": destinations,
        },
        numeric={
            "processes": run.process_count,
            "binaries_n": len(binaries),
            "writes_n": len(writes),
            "destinations_n": len(destinations),
        },
    )


def score_run(
    store: BaselineStore,
    *,
    artefact_id: int,
    skill_id: str,
    record_id: int,
    ts: str,
) -> BehaviourAlertPayload | None:
    """Score the run stored as `record_id`; append and return its alert, or None.

    Only runs recorded before it form the history. A run that already has an alert is not
    alerted again.
    """
    records = store.read_records()
    runs = _runs(records, skill_id)
    latest = next((obs for rid, obs in runs if rid == record_id), None)
    if latest is None:
        raise ValueError(f"record {record_id} is not a behaviour record of {skill_id}")
    alerted = _alerted_record_ids(records, skill_id)
    if record_id in alerted:
        return None
    history = [(obs, rid in alerted) for rid, obs in runs if rid < record_id]
    result = score(baseline(history, SKILL_SCORER), latest, SKILL_SCORER)
    if not result.alert:
        return None
    payload = BehaviourAlertPayload(
        code=DRIFT_CODE,
        skill_id=skill_id,
        observation_record_id=record_id,
        composite_milli=result.composite_milli,
        features=[
            DriftFeature(
                feature=item.feature,
                how=item.how,
                values=list(item.values),
                score_milli=item.score_milli,
                threshold_milli=item.threshold_milli,
            )
            for item in result.drifted
        ],
        window=SKILL_SCORER.window,
        scorer_version=SCORER_VERSION,
        detail=f"{skill_id} changed how it behaves: " + "; ".join(describe(result.drifted)),
    )
    append_event(store, artefact_id, "alert", payload, ts)
    return payload


def record_score_failure(
    store: BaselineStore,
    *,
    artefact_id: int,
    skill_id: str,
    record_id: int,
    error: Exception,
    ts: str,
) -> None:
    """Leave a `skill_score_failed` record for a run that could not be scored."""
    detail = f"{type(error).__name__}: {error}"[:200]
    payload = SkillScoreFailedPayload(
        skill_id=skill_id, observation_record_id=record_id, detail=detail
    )
    append_event(store, artefact_id, "alert", payload, ts)


def describe(drifts: Sequence[Drift]) -> list[str]:
    """One phrase per drifted feature, for the alert's `detail`."""
    phrases = []
    for item in drifts:
        if item.how == "never_seen":
            phrases.append(f"{item.feature} never seen: {', '.join(item.values)}")
        else:
            z = f"{item.score_milli // 1000}.{item.score_milli % 1000 // 100}"
            phrases.append(f"{item.feature} {item.values[0]} (z {z})")
    return phrases


def _runs(records: Sequence[StoredRecord], skill_id: str) -> list[tuple[int, Observation]]:
    """This skill's runs as (record id, observation), in chain order."""
    found: list[tuple[int, Observation]] = []
    for record in records:
        if record.kind != "behaviour":
            continue
        payload = _json(record)
        if payload is None or payload.get("skill_id") != skill_id:
            continue  # another skill's run, or an MCP call
        try:
            run = SkillBehaviourPayload.model_validate(payload)
        except ValidationError:
            continue  # a skills payload this version does not understand
        found.append((record.id, observation_of(run)))
    return found


def _alerted_record_ids(records: Sequence[StoredRecord], skill_id: str) -> set[int]:
    """Behaviour record ids that already raised `skill_behaviour_drift` for this skill."""
    found: set[int] = set()
    for record in records:
        if record.kind != "alert":
            continue
        payload = _json(record)
        if payload is None or payload.get("code") != DRIFT_CODE:
            continue
        if payload.get("skill_id") != skill_id:
            continue
        record_id = payload.get("observation_record_id")
        if isinstance(record_id, int) and not isinstance(record_id, bool):
            found.add(record_id)
    return found


def _json(record: StoredRecord) -> dict[str, Any] | None:
    try:
        value = json.loads(record.payload)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None
