"""Per-skill behavioural profile (T-15, feature half).

A profile is built from the behaviour records the collector stores (T-11), over the last 100
invocations of a skill. It is derived on demand and never stored: the only evidence is the
hash-chained records themselves.

Categorical features are support sets: every program run, file-write root and destination
seen in the window, with the number of invocations that showed it. Numeric features are
integer summaries of a per-invocation count. Deciding whether a new invocation deviates
(z-score, never-seen value, threshold) is the shared scorer's job (T-16); a profile only says
what normal has looked like and whether enough has been seen to judge.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from cim.common.schema.skills import SkillBehaviourPayload
from cim.common.store import BaselineStore

WINDOW = 100  # invocations a profile looks back over
WARMUP = 30  # invocations needed before a profile can be scored against

Support = tuple[tuple[str, int], ...]  # (value, invocations in the window that showed it)


@dataclass(frozen=True)
class Numeric:
    """Integer summary of one per-invocation number over the window.

    Count, sum and sum of squares give the mean and variance exactly, without a float ever
    entering a profile.
    """

    count: int
    total: int
    total_squares: int
    minimum: int
    maximum: int

    @classmethod
    def of(cls, values: Iterable[int]) -> Numeric:
        series = list(values)
        if not series:
            return cls(0, 0, 0, 0, 0)
        return cls(len(series), sum(series), sum(v * v for v in series), min(series), max(series))

    def render(self) -> str:
        return (
            str(self.minimum) if self.minimum == self.maximum else f"{self.minimum}-{self.maximum}"
        )


@dataclass(frozen=True)
class SkillProfile:
    """What normal has looked like for one skill."""

    skill_id: str
    observations: int
    warmed_up: bool
    binaries: Support
    write_targets: Support
    destinations: Support  # "dest_class:port"
    processes: Numeric
    binaries_per_invocation: Numeric
    writes_per_invocation: Numeric
    destinations_per_invocation: Numeric
    duration_us: Numeric  # wall-clock time: real, but different on every run

    def stable(self) -> dict[str, Any]:
        """The profile without timing: identical for identical behaviour, run after run."""
        return {
            "skill_id": self.skill_id,
            "observations": self.observations,
            "warmed_up": self.warmed_up,
            "binaries": self.binaries,
            "write_targets": self.write_targets,
            "destinations": self.destinations,
            "processes": self.processes,
            "binaries_per_invocation": self.binaries_per_invocation,
            "writes_per_invocation": self.writes_per_invocation,
            "destinations_per_invocation": self.destinations_per_invocation,
        }

    def render(self) -> str:
        state = "warmed_up" if self.warmed_up else f"warming_up {self.observations}/{WARMUP}"

        def names(support: Support) -> str:
            return ",".join(value for value, _count in support) or "-"

        return (
            f"{self.skill_id}: {state} window={self.observations} "
            f"processes={self.processes.render()} binaries={names(self.binaries)} "
            f"writes={names(self.write_targets)} destinations={names(self.destinations)}"
        )


def _support(rows: list[list[str]]) -> Support:
    seen: Counter[str] = Counter()
    for row in rows:
        seen.update(set(row))
    return tuple(sorted(seen.items()))


def build_profile(skill_id: str, invocations: list[SkillBehaviourPayload]) -> SkillProfile:
    """Profile from behaviour payloads in the order they were recorded; the last WINDOW count."""
    window = invocations[-WINDOW:]
    binaries = [list(item.binaries_executed) for item in window]
    writes = [list(item.file_write_targets) for item in window]
    destinations = [[f"{e.dest_class}:{e.port}" for e in item.egress] for item in window]
    return SkillProfile(
        skill_id=skill_id,
        observations=len(window),
        warmed_up=len(window) >= WARMUP,
        binaries=_support(binaries),
        write_targets=_support(writes),
        destinations=_support(destinations),
        processes=Numeric.of(item.process_count for item in window),
        binaries_per_invocation=Numeric.of(len(set(row)) for row in binaries),
        writes_per_invocation=Numeric.of(len(set(row)) for row in writes),
        destinations_per_invocation=Numeric.of(len(set(row)) for row in destinations),
        duration_us=Numeric.of(item.duration_us for item in window),
    )


def behaviour_history(store: BaselineStore) -> dict[str, list[SkillBehaviourPayload]]:
    """Every skill behaviour record in the store, per skill, oldest first."""
    history: dict[str, list[SkillBehaviourPayload]] = {}
    for record in store.read_records():
        if record.kind != "behaviour":
            continue
        payload = json.loads(record.payload)
        if not isinstance(payload, dict) or "skill_id" not in payload:
            continue  # an MCP tool call
        try:
            invocation = SkillBehaviourPayload.model_validate(payload)
        except ValidationError:
            continue  # not a skills payload this version understands
        history.setdefault(invocation.skill_id, []).append(invocation)
    return history


def profiles(store: BaselineStore, skill_id: str | None = None) -> list[SkillProfile]:
    """One profile per skill that has behaviour records, sorted by skill id."""
    history = behaviour_history(store)
    wanted = [skill_id] if skill_id is not None else sorted(history)
    return [build_profile(name, history[name]) for name in wanted if name in history]
