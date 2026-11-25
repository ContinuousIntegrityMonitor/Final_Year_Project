"""Skills half of the T-17 attack pack: A3 trigger payload and A4 legitimate update.

Each attack runs on a fresh copy of the seed corpus, never on the corpus itself (A4 edits
files), against a store of its own:

1. baseline every skill, then warm the attacked skill up with its scripted benign run;
2. the attack step;
3. a sweep, and one more run of the skill under the collector;
4. the checks the plan sets for the attack.

A3 (`meeting-brief`): the attack step is one run whose input mentions the trigger word. The
input file is outside the skill, so the skill's files and tree digest must stay exactly as
baselined; the run must show a destination the warm-up never had. Detector: T-16.

A4 (`word-count`): the attack step is a legitimate update copied over the skill. The sweep
must record it (detector: T-08 / T-10), and the run after it must show nothing the warm-up
had not shown, so no behavioural alert can follow.

The behavioural detector is the T-16 scorer: `record_behaviour` scores every run and writes a
`skill_behaviour_drift` alert when one leaves the learned pattern. A3 passes only if that alert
names the new destination; A4 passes only if no alert follows the update. `novel_values` (the
never-seen comparison, docs/T16_SHARED_SCORER_DESIGN.md section 3) stays in the report as a
plain cross-check of what the scorer saw.
"""

from __future__ import annotations

import shutil
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cim.common.schema.alerts import BehaviourAlertPayload
from cim.common.schema.skills import SkillBehaviourPayload, SkillIntegrityPayload
from cim.common.store import BaselineStore
from cim.skills.collector import observe, record_behaviour
from cim.skills.corpus import load_manifest
from cim.skills.envelope import WARMUP, SkillProfile, profiles
from cim.skills.inventory import describe_skill, sweep, take_inventory, write_baselines
from cim.skills.runner import Skill, discover_skills

AttackId = Literal["A3", "A4"]
ATTACKS_DIRNAME = "_attacks"  # under the corpus root; not a skill (no SKILL.md of its own)
A3_SKILL = "meeting-brief"
A3_INPUT = Path("t17-a3-trigger") / "notes-quarterly.md"
A4_SKILL = "word-count"
A4_UPDATE = Path("t17-a4-update") / "word-count"


@dataclass(frozen=True)
class AttackReport:
    attack: AttackId
    skill_id: str
    warmup_runs: int
    profile: SkillProfile  # what normal looked like before the attack step
    changes: tuple[SkillIntegrityPayload, ...]  # what the sweep after the attack step recorded
    digest_before: str
    digest_after: str
    run: SkillBehaviourPayload  # the run after the attack step
    novel: tuple[str, ...]  # values in that run the warm-up never showed
    alert: BehaviourAlertPayload | None  # the scorer's alert on that run, if it raised one
    received: bytes | None  # what the local listener got; None when no local listener ran
    passed: bool
    expected: str


def novel_values(profile: SkillProfile, run: SkillBehaviourPayload) -> list[str]:
    """Categorical values in `run` that the profile's window never showed, as `feature: value`.

    This is the never-seen check of the T-16 design, kept as a cross-check of the scorer.
    """
    seen = {
        "binaries": {value for value, _ in profile.binaries},
        "write_targets": {value for value, _ in profile.write_targets},
        "destinations": {value for value, _ in profile.destinations},
    }
    now = {
        "binaries": set(run.binaries_executed),
        "write_targets": set(run.file_write_targets),
        "destinations": {f"{e.dest_class}:{e.port}" for e in run.egress},
    }
    return [
        f"{feature}: {value}" for feature in seen for value in sorted(now[feature] - seen[feature])
    ]


@contextmanager
def local_listener() -> Iterator[tuple[int, bytearray]]:
    """A one-connection TCP listener on loopback. Yields its port and the bytes it received."""
    received = bytearray()
    server = socket.create_server(("127.0.0.1", 0))
    server.settimeout(10)

    def accept() -> None:
        try:
            connection, _ = server.accept()
        except OSError:
            return
        with connection:
            connection.settimeout(5)
            while chunk := connection.recv(65536):
                received.extend(chunk)

    thread = threading.Thread(target=accept, name="cim-attack-listener", daemon=True)
    thread.start()
    try:
        yield int(server.getsockname()[1]), received
    finally:
        thread.join(timeout=10)
        server.close()


def prepare(work: Path, corpus: Path) -> Path:
    """Copy the corpus into `work` (which must be empty or missing); returns the copy's root."""
    if work.exists() and any(work.iterdir()):
        raise FileExistsError(f"{work} is not empty; attacks start from a fresh copy")
    root = work / "skills"
    shutil.copytree(corpus, root)
    return root


def _skill(root: Path, skill_id: str) -> Skill:
    return next(skill for skill in discover_skills(root) if skill.skill_id == skill_id)


def _warm_up(store: BaselineStore, root: Path, skill_id: str, runs: int) -> SkillProfile:
    write_baselines(store, take_inventory([root]))
    skill = _skill(root, skill_id)
    scripted = load_manifest(root)[skill_id].runs[0]
    for _ in range(runs):
        record_behaviour(store, skill, observe(skill, skill.path / scripted.script, scripted.args))
    return profiles(store, skill_id)[0]


def run_a3(
    store: BaselineStore,
    root: Path,
    *,
    warmup: int = WARMUP,
    listener: tuple[str, int] | None = None,
) -> AttackReport:
    """Warm `meeting-brief` up, then run it once on notes that hold the trigger word.

    With no `listener`, a local one on loopback receives what the skill sends, so the report
    can show it. On VM-MON pass the lab listener's address instead.
    """
    profile = _warm_up(store, root, A3_SKILL, warmup)
    skill = _skill(root, A3_SKILL)
    before = describe_skill(skill).tree_digest
    script = skill.path / load_manifest(root)[A3_SKILL].runs[0].script
    trigger = str((root / ATTACKS_DIRNAME / A3_INPUT).resolve())
    received: bytes | None = None
    if listener is None:
        with local_listener() as (port, got):
            seen = observe(skill, script, (trigger, "--host", "127.0.0.1", "--port", str(port)))
        received = bytes(got)
    else:
        host, port = listener
        seen = observe(skill, script, (trigger, "--host", host, "--port", str(port)))
    alert = record_behaviour(store, skill, seen).alert
    changes = sweep(store, [root]).events
    after = describe_skill(_skill(root, A3_SKILL)).tree_digest
    run = seen.payload()
    novel = novel_values(profile, run)
    passed = (
        not changes
        and before == after
        and alert is not None
        and any(f.feature == "destinations" and f.how == "never_seen" for f in alert.features)
        and (received is None or b'"env_names"' in received)
    )
    return AttackReport(
        attack="A3",
        skill_id=A3_SKILL,
        warmup_runs=warmup,
        profile=profile,
        changes=changes,
        digest_before=before,
        digest_after=after,
        run=run,
        novel=tuple(novel),
        alert=alert,
        received=received,
        passed=passed,
        expected="files unchanged; a T-16 behaviour alert naming a never-seen destination",
    )


def run_a4(store: BaselineStore, root: Path, *, warmup: int = WARMUP) -> AttackReport:
    """Warm `word-count` up, apply its legitimate update, then run it once more."""
    profile = _warm_up(store, root, A4_SKILL, warmup)
    skill = _skill(root, A4_SKILL)
    before = describe_skill(skill).tree_digest
    update = root / ATTACKS_DIRNAME / A4_UPDATE
    for source in sorted(path for path in update.rglob("*") if path.is_file()):
        target = skill.path / source.relative_to(update)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    changes = sweep(store, [root]).events
    skill = _skill(root, A4_SKILL)  # the update may add or remove helpers
    after = describe_skill(skill).tree_digest
    scripted = load_manifest(root)[A4_SKILL].runs[0]
    seen = observe(skill, skill.path / scripted.script, scripted.args)
    alert = record_behaviour(store, skill, seen).alert
    run = seen.payload()
    novel = novel_values(profile, run)
    passed = bool(changes) and before != after and alert is None and not novel
    return AttackReport(
        attack="A4",
        skill_id=A4_SKILL,
        warmup_runs=warmup,
        profile=profile,
        changes=changes,
        digest_before=before,
        digest_after=after,
        run=run,
        novel=tuple(novel),
        alert=alert,
        received=None,
        passed=passed,
        expected="the update recorded as file changes (T-08/T-10); no T-16 behaviour alert",
    )


def render(report: AttackReport) -> list[str]:
    """Plain lines for `python -m cim.skills attack`."""
    name = f"attack {report.attack}"
    lines = [
        f"{name}: {report.skill_id} warmed up over {report.warmup_runs} runs "
        f"(destinations seen: {', '.join(v for v, _ in report.profile.destinations) or 'none'})",
    ]
    if report.changes:
        listed = ", ".join(f"{c.change} {c.path}" for c in report.changes)
        lines.append(f"{name}: sweep recorded {len(report.changes)} file change(s): {listed}")
    else:
        lines.append(f"{name}: sweep recorded no file change")
    same = "unchanged" if report.digest_before == report.digest_after else "changed"
    lines.append(
        f"{name}: tree digest {same} ({report.digest_before[:12]}… -> {report.digest_after[:12]}…)"
    )
    egress = ", ".join(f"{e.dest_class}:{e.port}" for e in report.run.egress) or "none"
    lines.append(f"{name}: run after the attack step: egress {egress}")
    if report.received is not None:
        lines.append(
            f"{name}: local listener received {len(report.received)} bytes: "
            f"{report.received[:200]!r}"
        )
    lines.append(f"{name}: never seen during warm-up: {', '.join(report.novel) or 'nothing'}")
    if report.alert is not None:
        lines.append(f"{name}: behaviour alert: {report.alert.detail}")
    else:
        lines.append(f"{name}: behaviour alert: none")
    lines.append(f"{name}: expected {report.expected}: {'PASS' if report.passed else 'FAIL'}")
    return lines
