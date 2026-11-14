"""Skills artefact inventory and file-level change detection (T-08).

`take_inventory` hashes every skill under the configured roots. `write_baselines` stores one
artefact record per skill. `sweep` compares the skills on disk with what the store already
knows and records one integrity event per changed file.

What the store knows about a skill is its artefact record plus every integrity event recorded
after it. So a change is reported once, not again on every later sweep, and the first
baseline is never rewritten.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from cim.common.schema.envelope import Artefact, Event, Kind
from cim.common.schema.skills import SkillArtefactPayload, SkillIntegrityPayload
from cim.common.store import BaselineStore
from cim.skills.digest import hash_files, record_path, tree_digest
from cim.skills.runner import Skill, discover_skills

ROOTS_ENV = "CIM_SKILL_ROOTS"
DEFAULT_ORIGIN = "vm-mon"


@dataclass
class KnownSkill:
    """What the store currently says about one skill."""

    artefact_id: int
    files: dict[str, str]  # path -> sha256


@dataclass(frozen=True)
class SweepResult:
    new_skills: tuple[str, ...]
    events: tuple[SkillIntegrityPayload, ...]


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def skill_roots(env: Mapping[str, str] | None = None) -> list[Path]:
    """Skill roots from CIM_SKILL_ROOTS (separated like PATH)."""
    source = os.environ if env is None else env
    return [Path(part) for part in source.get(ROOTS_ENV, "").split(os.pathsep) if part]


def describe_skill(skill: Skill, skill_id: str | None = None) -> SkillArtefactPayload:
    files = hash_files(skill.path)
    return SkillArtefactPayload(
        skill_id=skill_id or skill.skill_id,
        name=skill.name,
        description=skill.description,
        root=record_path(str(skill.path.resolve())),
        files=files,
        tree_digest=tree_digest(files),
    )


def take_inventory(roots: Iterable[Path]) -> dict[str, SkillArtefactPayload]:
    """One payload per installed skill, keyed by skill id.

    A root that does not exist has no skills. If the same directory name appears under more
    than one root, the later ones are recorded as `name#2`, `name#3` in root order, so a
    second copy can neither hide behind the first nor stop the inventory.
    """
    inventory: dict[str, SkillArtefactPayload] = {}
    copies: dict[str, int] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for skill in discover_skills(root):
            copies[skill.skill_id] = copies.get(skill.skill_id, 0) + 1
            count = copies[skill.skill_id]
            skill_id = skill.skill_id if count == 1 else f"{skill.skill_id}#{count}"
            inventory[skill_id] = describe_skill(skill, skill_id)
    return inventory


def known_skills(store: BaselineStore) -> dict[str, KnownSkill]:
    """Replay the store: each artefact record, then the integrity events that follow it."""
    known: dict[str, KnownSkill] = {}
    for record in store.read_records():
        if record.kind not in ("artefact", "integrity"):
            continue
        payload = json.loads(record.payload)
        if not isinstance(payload, dict) or not isinstance(payload.get("skill_id"), str):
            continue  # an MCP record
        try:
            if record.kind == "artefact":
                baseline = SkillArtefactPayload.model_validate(payload)
                files = {item.path: item.sha256 for item in baseline.files}
                known[baseline.skill_id] = KnownSkill(record.artefact_id, files)
                continue
            change = SkillIntegrityPayload.model_validate(payload)
        except ValidationError:
            continue  # not a skills payload this version understands
        skill = known.get(change.skill_id)
        if skill is None:
            continue
        if change.change == "rename" and change.old_path is not None:
            skill.files.pop(change.old_path, None)
        if change.change == "delete":
            skill.files.pop(change.path, None)
        elif change.new_sha256 is not None:
            skill.files[change.path] = change.new_sha256
    return known


def diff_files(
    skill_id: str, known: Mapping[str, str], current: Mapping[str, str]
) -> list[SkillIntegrityPayload]:
    """File-level differences between what is known and what is on disk, sorted by path.

    A new path whose content matches a path that disappeared is one rename, not a delete
    plus a create.
    """
    removed = sorted(known.keys() - current.keys())
    events: list[SkillIntegrityPayload] = []
    for path in sorted(current.keys() - known.keys()):
        digest = current[path]
        source = next((old for old in removed if known[old] == digest), None)
        if source is None:
            events.append(
                SkillIntegrityPayload(
                    skill_id=skill_id, change="create", path=path, new_sha256=digest
                )
            )
            continue
        removed.remove(source)
        events.append(
            SkillIntegrityPayload(
                skill_id=skill_id,
                change="rename",
                path=path,
                old_path=source,
                old_sha256=digest,
                new_sha256=digest,
            )
        )
    for path in removed:
        events.append(
            SkillIntegrityPayload(
                skill_id=skill_id, change="delete", path=path, old_sha256=known[path]
            )
        )
    for path in sorted(known.keys() & current.keys()):
        if known[path] != current[path]:
            events.append(
                SkillIntegrityPayload(
                    skill_id=skill_id,
                    change="modify",
                    path=path,
                    old_sha256=known[path],
                    new_sha256=current[path],
                )
            )
    return sorted(events, key=lambda event: event.path)


def _append(store: BaselineStore, artefact_id: int, kind: Kind, model: BaseModel, ts: str) -> None:
    payload = model.model_dump(mode="json")
    skill_id = payload["skill_id"]
    # Go through the event contract, so nothing the contract rejects reaches the store.
    Event(ts=ts, artefact=Artefact(type="skill", skill=skill_id), kind=kind, payload=payload)
    store.append_record(artefact_id, kind, payload, ts)


def _write_baseline(
    store: BaselineStore, payload: SkillArtefactPayload, origin: str, ts: str
) -> KnownSkill:
    artefact_id = store.append_artefact("skill", payload.skill_id, origin)
    _append(store, artefact_id, "artefact", payload, ts)
    return KnownSkill(artefact_id, {item.path: item.sha256 for item in payload.files})


def write_baselines(
    store: BaselineStore,
    inventory: Mapping[str, SkillArtefactPayload],
    *,
    origin: str = DEFAULT_ORIGIN,
    ts: str | None = None,
) -> list[str]:
    """Store a baseline for every skill that has none yet. Returns the ids written.

    Running it again writes nothing: N installed skills give N baselines.
    """
    stamp = ts or utc_now()
    known = known_skills(store)
    written: list[str] = []
    with store.transaction():
        for skill_id in sorted(inventory.keys() - known.keys()):
            _write_baseline(store, inventory[skill_id], origin, stamp)
            written.append(skill_id)
    return written


def sweep(
    store: BaselineStore,
    roots: Iterable[Path],
    *,
    origin: str = DEFAULT_ORIGIN,
    ts: str | None = None,
) -> SweepResult:
    """Compare the skills on disk with the store and record every difference.

    A skill the store has never seen gets a baseline and a `create` event per file. A skill
    that is gone gets a `delete` event per file. A sweep with nothing to report writes nothing.
    """
    stamp = ts or utc_now()
    current = take_inventory(roots)
    known = known_skills(store)
    new_skills: list[str] = []
    events: list[SkillIntegrityPayload] = []
    with store.transaction():
        for skill_id in sorted(current.keys() | known.keys()):
            payload = current.get(skill_id)
            skill = known.get(skill_id)
            before: Mapping[str, str] = skill.files if skill is not None else {}
            if skill is None:
                assert payload is not None
                skill = _write_baseline(store, payload, origin, stamp)
                new_skills.append(skill_id)
            on_disk = {item.path: item.sha256 for item in payload.files} if payload else {}
            for event in diff_files(skill_id, before, on_disk):
                _append(store, skill.artefact_id, "integrity", event, stamp)
                events.append(event)
    return SweepResult(tuple(new_skills), tuple(events))
