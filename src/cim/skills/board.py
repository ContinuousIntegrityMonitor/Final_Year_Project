"""Skills read model for the status board (U1).

The board (`cim.dashboard.board`, Hamza's) reads one store that both sides write to. Its
lists are MCP lists: a skill integrity record shown there becomes a schema change with no
server and no tool, and a skill run becomes a call to tool `unknown`. This module gives the
board what it needs to show skills as skills:

- `is_skill_payload` tells a skill record from an MCP record, so the MCP lists can skip it.
- `skills_board` turns the records the board has already read into one skills section.
- `as_dict` is the JSON shape of that section (`docs/U1_SKILLS_BOARD_SHAPE.md`).
- `rail_label` names a skill record on the fingerprint rail.

Everything is derived from the records passed in. Nothing is read twice and nothing is
written, so the board's "read-only" promise holds for the skills section too.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from cim.common.schema.skills import (
    SkillArtefactPayload,
    SkillBehaviourPayload,
    SkillIntegrityPayload,
)
from cim.common.store import BaselineStore, StoredRecord
from cim.skills.envelope import WARMUP, WINDOW, SkillProfile, Support, build_profile, history_of
from cim.skills.inventory import fold_known

SHAPE_VERSION = 1
LIST_LIMIT = 40  # newest changes, runs and alerts sent to the page

State = Literal["healthy", "learning", "warning"]
IntegrityState = Literal["unchanged", "changed", "removed"]
BehaviourState = Literal["empty", "learning", "healthy"]


def is_skill_payload(payload: object) -> bool:
    """True for a record written by the skills side. MCP payloads never carry `skill_id`."""
    return isinstance(payload, Mapping) and isinstance(payload.get("skill_id"), str)


@dataclass(frozen=True)
class SkillChange:
    record_id: int
    ts: str
    skill_id: str
    change: str  # create | modify | delete | rename
    path: str
    old_path: str | None
    old_sha256: str | None
    new_sha256: str | None


@dataclass(frozen=True)
class SkillRun:
    record_id: int
    ts: str
    skill_id: str
    invocation_id: str
    process_count: int
    binaries: tuple[str, ...]
    write_targets: tuple[str, ...]
    destinations: tuple[str, ...]  # "dest_class:port"
    duration_us: int


@dataclass(frozen=True)
class SkillAlert:
    record_id: int
    ts: str
    skill_id: str
    code: str
    detail: str


@dataclass
class _Baseline:
    record_id: int
    ts: str
    payload: SkillArtefactPayload


@dataclass(frozen=True)
class SkillRow:
    """One installed skill: does it still match its baseline, and how has it behaved."""

    skill_id: str
    name: str
    description: str
    root: str
    state: State
    integrity: IntegrityState
    baseline_record_id: int | None
    baseline_ts: str
    baseline_files: int
    tree_digest: str
    files_now: int
    change_count: int
    changed_paths: tuple[str, ...]
    last_change_ts: str
    behaviour: BehaviourState
    runs: int
    profile: SkillProfile | None
    last_run_ts: str
    alert_count: int


@dataclass(frozen=True)
class SkillsBoard:
    skills: tuple[SkillRow, ...]
    changes: tuple[SkillChange, ...]  # newest first, at most LIST_LIMIT
    runs: tuple[SkillRun, ...]  # newest first, at most LIST_LIMIT
    alerts: tuple[SkillAlert, ...]  # newest first, at most LIST_LIMIT
    total_changes: int
    total_runs: int
    total_alerts: int

    def count(self, state: str) -> int:
        return sum(1 for row in self.skills if state in (row.state, row.integrity))


@dataclass
class _Collected:
    baselines: dict[str, _Baseline] = field(default_factory=dict)
    changes: list[SkillChange] = field(default_factory=list)
    runs: list[SkillRun] = field(default_factory=list)
    alerts: list[SkillAlert] = field(default_factory=list)


def _payload(record: StoredRecord) -> dict[str, Any] | None:
    try:
        value = json.loads(record.payload)
    except ValueError:
        return None
    return value if is_skill_payload(value) else None


def _collect(records: Sequence[StoredRecord]) -> _Collected:
    found = _Collected()
    for record in records:
        payload = _payload(record)
        if payload is None:
            continue
        skill_id = str(payload["skill_id"])
        try:
            if record.kind == "artefact":
                baseline = SkillArtefactPayload.model_validate(payload)
                found.baselines[skill_id] = _Baseline(record.id, record.ts, baseline)
            elif record.kind == "integrity":
                change = SkillIntegrityPayload.model_validate(payload)
                found.changes.append(
                    SkillChange(
                        record_id=record.id,
                        ts=record.ts,
                        skill_id=skill_id,
                        change=change.change,
                        path=change.path,
                        old_path=change.old_path,
                        old_sha256=change.old_sha256,
                        new_sha256=change.new_sha256,
                    )
                )
            elif record.kind == "behaviour":
                run = SkillBehaviourPayload.model_validate(payload)  # as history_of parses it
                found.runs.append(
                    SkillRun(
                        record_id=record.id,
                        ts=record.ts,
                        skill_id=skill_id,
                        invocation_id=run.invocation_id,
                        process_count=run.process_count,
                        binaries=tuple(run.binaries_executed),
                        write_targets=tuple(run.file_write_targets),
                        destinations=tuple(f"{e.dest_class}:{e.port}" for e in run.egress),
                        duration_us=run.duration_us,
                    )
                )
            elif record.kind == "alert":
                found.alerts.append(
                    SkillAlert(
                        record_id=record.id,
                        ts=record.ts,
                        skill_id=skill_id,
                        code=str(payload.get("code") or "alert"),
                        detail=str(payload.get("detail") or ""),
                    )
                )
        except ValidationError:
            continue  # a skills payload this version does not understand
    return found


def skills_board(records: Sequence[StoredRecord]) -> SkillsBoard:
    """The skills section of the board, from the store's records in chain order."""
    found = _collect(records)
    history = history_of(records)
    known = fold_known(records)
    skill_ids = sorted(found.baselines.keys() | history.keys())
    rows: list[SkillRow] = []
    for skill_id in skill_ids:
        baseline = found.baselines.get(skill_id)
        changes = [c for c in found.changes if c.skill_id == skill_id]
        runs = [r for r in found.runs if r.skill_id == skill_id]
        alert_count = sum(1 for a in found.alerts if a.skill_id == skill_id)
        now = known.get(skill_id)
        integrity: IntegrityState = "unchanged"
        if baseline is not None and now is not None and not now.files:
            integrity = "removed"
        elif changes:
            integrity = "changed"
        profile = build_profile(skill_id, history[skill_id]) if skill_id in history else None
        behaviour: BehaviourState = "empty"
        if profile is not None:
            behaviour = "healthy" if profile.warmed_up else "learning"
        state: State = "learning"
        if integrity != "unchanged" or alert_count:
            state = "warning"
        elif behaviour == "healthy":
            state = "healthy"
        files = baseline.payload.files if baseline is not None else []
        rows.append(
            SkillRow(
                skill_id=skill_id,
                name=baseline.payload.name if baseline is not None else skill_id,
                description=baseline.payload.description if baseline is not None else "",
                root=baseline.payload.root if baseline is not None else "",
                state=state,
                integrity=integrity,
                baseline_record_id=baseline.record_id if baseline is not None else None,
                baseline_ts=baseline.ts if baseline is not None else "",
                baseline_files=len(files),
                tree_digest=baseline.payload.tree_digest if baseline is not None else "",
                files_now=len(now.files) if now is not None else 0,
                change_count=len(changes),
                changed_paths=tuple(sorted({c.path for c in changes})),
                last_change_ts=changes[-1].ts if changes else "",
                behaviour=behaviour,
                runs=len(runs),
                profile=profile,
                last_run_ts=runs[-1].ts if runs else "",
                alert_count=alert_count,
            )
        )
    return SkillsBoard(
        skills=tuple(rows),
        changes=tuple(reversed(found.changes[-LIST_LIMIT:])),
        runs=tuple(reversed(found.runs[-LIST_LIMIT:])),
        alerts=tuple(reversed(found.alerts[-LIST_LIMIT:])),
        total_changes=len(found.changes),
        total_runs=len(found.runs),
        total_alerts=len(found.alerts),
    )


def load_skills_board(db: Path) -> SkillsBoard:
    """Convenience for the CLI: read the store once and build the skills section."""
    with BaselineStore(db) as store:
        return skills_board(store.read_records())


def rail_label(kind: str, payload: Mapping[str, Any]) -> tuple[str, str] | None:
    """(mark, label) for a skill record on the fingerprint rail; None for an MCP record."""
    if not is_skill_payload(payload):
        return None
    skill_id = str(payload["skill_id"])
    if kind == "artefact":
        return "baseline", f"{skill_id}: baseline"
    if kind == "integrity":
        return "change", f"{skill_id}: {payload.get('change', 'change')} {payload.get('path', '')}"
    if kind == "behaviour":
        return "call", f"{skill_id}: run"
    if kind == "alert":
        return "alert", f"{skill_id}: {payload.get('detail') or payload.get('code') or 'alert'}"
    return None


def _support(values: Support) -> list[dict[str, Any]]:
    return [{"value": value, "runs": runs} for value, runs in values]


def as_dict(board: SkillsBoard) -> dict[str, Any]:
    """JSON for the page. Shape version 1; see docs/U1_SKILLS_BOARD_SHAPE.md."""
    return {
        "version": SHAPE_VERSION,
        "warmup": WARMUP,
        "window": WINDOW,
        "summary": {
            "skills": len(board.skills),
            "healthy": board.count("healthy"),
            "learning": board.count("learning"),
            "warning": board.count("warning"),
            "changed": board.count("changed"),
            "removed": board.count("removed"),
            "changes": board.total_changes,
            "runs": board.total_runs,
            "alerts": board.total_alerts,
        },
        "skills": [_row(row) for row in board.skills],
        "changes": [
            {
                "record_id": c.record_id,
                "ts": c.ts,
                "skill_id": c.skill_id,
                "change": c.change,
                "path": c.path,
                "old_path": c.old_path,
                "old_sha256": c.old_sha256,
                "new_sha256": c.new_sha256,
            }
            for c in board.changes
        ],
        "runs": [
            {
                "record_id": r.record_id,
                "ts": r.ts,
                "skill_id": r.skill_id,
                "invocation_id": r.invocation_id,
                "process_count": r.process_count,
                "binaries": list(r.binaries),
                "write_targets": list(r.write_targets),
                "destinations": list(r.destinations),
                "duration_us": r.duration_us,
            }
            for r in board.runs
        ],
        "alerts": [
            {
                "record_id": a.record_id,
                "ts": a.ts,
                "skill_id": a.skill_id,
                "code": a.code,
                "detail": a.detail,
            }
            for a in board.alerts
        ],
    }


def _row(row: SkillRow) -> dict[str, Any]:
    profile = row.profile
    return {
        "skill_id": row.skill_id,
        "name": row.name,
        "description": row.description,
        "root": row.root,
        "state": row.state,
        "alerts": row.alert_count,
        "integrity": {
            "state": row.integrity,
            "baseline_record_id": row.baseline_record_id,
            "baseline_ts": row.baseline_ts,
            "baseline_files": row.baseline_files,
            "tree_digest": row.tree_digest,
            "files_now": row.files_now,
            "changes": row.change_count,
            "changed_paths": list(row.changed_paths),
            "last_change_ts": row.last_change_ts,
        },
        "behaviour": {
            "state": row.behaviour,
            "runs": row.runs,
            "observations": profile.observations if profile else 0,
            "warmed_up": profile.warmed_up if profile else False,
            "last_run_ts": row.last_run_ts,
            "binaries": _support(profile.binaries) if profile else [],
            "write_targets": _support(profile.write_targets) if profile else [],
            "destinations": _support(profile.destinations) if profile else [],
            "processes": (
                {"min": profile.processes.minimum, "max": profile.processes.maximum}
                if profile
                else {"min": 0, "max": 0}
            ),
        },
    }


def render(board: SkillsBoard) -> list[str]:
    """Plain lines for `python -m cim.skills board`."""
    summary = as_dict(board)["summary"]
    lines = [
        f"skills: {summary['skills']} installed, {summary['warning']} warning, "
        f"{summary['learning']} learning, {summary['healthy']} healthy; "
        f"{summary['changes']} file changes, {summary['runs']} runs, {summary['alerts']} alerts"
    ]
    for row in board.skills:
        integrity: str = row.integrity
        if row.changed_paths:
            integrity += " (" + ", ".join(row.changed_paths) + ")"
        if row.behaviour == "empty":
            behaviour = f"no runs (0/{WARMUP})"
        elif row.behaviour == "learning" and row.profile is not None:
            behaviour = f"learning {row.profile.observations}/{WARMUP}"
        else:
            behaviour = "warmed up"
        lines.append(
            f"{row.skill_id}: {row.state} | files {integrity} | behaviour {behaviour}"
            + (f" | {row.alert_count} alert(s)" if row.alert_count else "")
        )
    return lines
