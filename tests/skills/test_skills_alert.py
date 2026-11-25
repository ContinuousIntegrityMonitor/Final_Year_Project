"""Skills behaviour alert (T-16, skills half; SYS-06, SYS-07, SYS-08)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from cim.common.schema.skills import Egress, SkillBehaviourPayload
from cim.common.store import BaselineStore
from cim.skills import collector
from cim.skills.alert import DRIFT_CODE, FAILED_CODE, describe, observation_of, score_run
from cim.skills.board import skills_board
from cim.skills.collector import Observation, record_behaviour
from cim.skills.corpus import default_root
from cim.skills.envelope import WARMUP
from cim.skills.inventory import append_event
from cim.skills.runner import discover_skills

TS = "2026-11-25T10:00:00Z"
SKILL = "notes-sync"
PUBLIC_443 = Egress(dest_class="public_ip", port=443)


def _run(
    n: int,
    *,
    skill_id: str = SKILL,
    binaries: tuple[str, ...] = ("/usr/bin/python3",),
    writes: tuple[str, ...] = ("~/notes",),
    egress: tuple[Egress, ...] = (),
    processes: int = 1,
) -> SkillBehaviourPayload:
    return SkillBehaviourPayload(
        skill_id=skill_id,
        invocation_id=f"inv-{n:04d}",
        cgroup_id=f"cim-skill-{skill_id}-inv-{n:04d}.scope",
        binaries_executed=list(binaries),
        file_write_targets=list(writes),
        egress=list(egress),
        process_count=processes,
        duration_us=1000 + n,  # different every run, and never scored
    )


def _skill(store: BaselineStore, skill_id: str = SKILL) -> int:
    return store.append_artefact("skill", skill_id, "test")


def _append(store: BaselineStore, aid: int, run: SkillBehaviourPayload) -> int:
    return append_event(store, aid, "behaviour", run, TS)


def _score(store: BaselineStore, aid: int, record_id: int, skill_id: str = SKILL) -> Any:
    return score_run(store, artefact_id=aid, skill_id=skill_id, record_id=record_id, ts=TS)


def _record_and_score(store: BaselineStore, aid: int, run: SkillBehaviourPayload) -> Any:
    return _score(store, aid, _append(store, aid, run), run.skill_id)


def _warm(store: BaselineStore, aid: int, count: int = WARMUP) -> None:
    for n in range(count):
        assert _record_and_score(store, aid, _run(n)) is None


def _alerts(store: BaselineStore) -> list[dict[str, Any]]:
    return [json.loads(r.payload) for r in store.read_records() if r.kind == "alert"]


def test_observation_counts_distinct_values() -> None:
    run = _run(1, binaries=("/usr/bin/sh", "/usr/bin/sh", "/usr/bin/curl"), processes=3)
    obs = observation_of(run)
    assert obs.categorical["binaries"] == frozenset({"/usr/bin/sh", "/usr/bin/curl"})
    assert obs.numeric == {"processes": 3, "binaries_n": 2, "writes_n": 1, "destinations_n": 0}


def test_sys08_benign_runs_never_alert(tmp_path: Path) -> None:
    """SYS-08: 130 benign runs with some spread in their counts give zero alerts."""
    with BaselineStore(tmp_path / "s.sqlite") as store:
        aid = _skill(store)
        for n in range(130):
            run = _run(n, processes=1 + n % 3, writes=("~/notes",) if n % 2 else ("~/notes", "~"))
            assert _record_and_score(store, aid, run) is None
        assert _alerts(store) == []


def test_no_alert_during_warm_up(tmp_path: Path) -> None:
    with BaselineStore(tmp_path / "s.sqlite") as store:
        aid = _skill(store)
        _warm(store, aid, WARMUP - 1)
        assert _record_and_score(store, aid, _run(99, egress=(PUBLIC_443,))) is None
        assert _alerts(store) == []


def test_sys06_never_seen_destination_alerts_and_names_it(tmp_path: Path) -> None:
    """SYS-06 / SYS-07: an A3-like run (new destination) alerts once warm, naming the feature."""
    with BaselineStore(tmp_path / "s.sqlite") as store:
        aid = _skill(store)
        _warm(store, aid)
        record_id = _append(store, aid, _run(99, egress=(PUBLIC_443,)))
        alert = _score(store, aid, record_id)
        assert alert is not None
        assert alert.code == DRIFT_CODE and alert.skill_id == SKILL
        assert alert.observation_record_id == record_id
        assert alert.composite_milli == 10_000
        # destinations_n goes 0 -> 1: z 1.0 under the sd floor, so it is not named.
        assert [(f.feature, f.how, f.values) for f in alert.features] == [
            ("destinations", "never_seen", ["public_ip:443"]),
        ]
        assert alert.window == 100 and alert.scorer_version == 1
        assert alert.detail == (
            "notes-sync changed how it behaves: destinations never seen: public_ip:443"
        )
        assert _alerts(store) == [alert.model_dump(mode="json")]
        assert store.verify_chain().ok


def test_alert_names_the_top_three_features(tmp_path: Path) -> None:
    """Four features drift; the alert keeps the three highest (ties by name)."""
    with BaselineStore(tmp_path / "s.sqlite") as store:
        aid = _skill(store)
        _warm(store, aid)
        run = _run(
            99,
            binaries=("/usr/bin/python3", "/usr/bin/curl", "/usr/bin/sh"),
            writes=("~/notes", "/tmp"),
            egress=(PUBLIC_443,),
            processes=8,  # z 7.0: drifted, but below the three never-seen features
        )
        alert = _record_and_score(store, aid, run)
        assert alert is not None
        assert [f.feature for f in alert.features] == ["binaries", "destinations", "write_targets"]
        assert alert.features[0].values == ["/usr/bin/curl", "/usr/bin/sh"]
        assert alert.composite_milli == 10_000


def test_process_count_needs_a_real_jump(tmp_path: Path) -> None:
    """The sd floor: 1 → 2 processes is z 1.0 (quiet); 1 → 6 is about z 5 (alert)."""
    with BaselineStore(tmp_path / "s.sqlite") as store:
        aid = _skill(store)
        _warm(store, aid)
        assert _record_and_score(store, aid, _run(98, processes=2)) is None
        alert = _record_and_score(store, aid, _run(99, processes=6))
        assert alert is not None
        # The 2-process run joined the window: n=31, S=32, spread=n²=961, above=154 → 4967.
        assert [(f.feature, f.score_milli) for f in alert.features] == [("processes", 4967)]


def test_a1_repeated_attack_alerts_every_time(tmp_path: Path) -> None:
    with BaselineStore(tmp_path / "s.sqlite") as store:
        aid = _skill(store)
        _warm(store, aid, 60)
        ids = []
        for n in range(5):
            alert = _record_and_score(store, aid, _run(100 + n, egress=(PUBLIC_443,)))
            assert alert is not None
            ids.append(alert.observation_record_id)
        assert len(set(ids)) == 5


def test_scores_the_named_record_not_the_newest(tmp_path: Path) -> None:
    """Two writers: a benign run lands after the attack, before the attack is scored."""
    with BaselineStore(tmp_path / "s.sqlite") as store:
        aid = _skill(store)
        _warm(store, aid)
        attack = _append(store, aid, _run(98, egress=(PUBLIC_443,)))
        benign = _append(store, aid, _run(99))
        alert = _score(store, aid, attack)
        assert alert is not None and alert.observation_record_id == attack
        assert _score(store, aid, benign) is None
        assert _score(store, aid, attack) is None  # already alerted: no second record
        assert len(_alerts(store)) == 1


def test_other_skills_and_mcp_calls_stay_out_of_the_history(tmp_path: Path) -> None:
    with BaselineStore(tmp_path / "s.sqlite") as store:
        aid = _skill(store)
        other = _skill(store, "dep-installer")
        for n in range(WARMUP):
            _append(store, other, _run(n, skill_id="dep-installer", egress=(PUBLIC_443,)))
        _warm(store, aid)
        alert = _record_and_score(store, aid, _run(99, egress=(PUBLIC_443,)))
        assert alert is not None and alert.features[0].feature == "destinations"


def test_unknown_record_is_refused(tmp_path: Path) -> None:
    with BaselineStore(tmp_path / "s.sqlite") as store:
        aid = _skill(store)
        other = _skill(store, "dep-installer")
        foreign = _append(store, other, _run(1, skill_id="dep-installer"))
        with pytest.raises(ValueError, match="not a behaviour record of notes-sync"):
            _score(store, aid, foreign)


def test_describe_rounds_z_down_to_one_decimal() -> None:
    from cim.common.scorer import Drift

    drift = Drift("processes", "z", ("6",), 4472, 4000)
    assert describe([drift]) == ["processes 6 (z 4.4)"]


def test_board_lists_the_alert(tmp_path: Path) -> None:
    """U1: the skills board's `alerts` fill in from the record, with no board change."""
    with BaselineStore(tmp_path / "s.sqlite") as store:
        aid = _skill(store)
        _warm(store, aid)
        alert = _record_and_score(store, aid, _run(99, egress=(PUBLIC_443,)))
        board = skills_board(store.read_records())
    assert [(a.skill_id, a.code, a.detail) for a in board.alerts] == [
        (SKILL, DRIFT_CODE, alert.detail)
    ]


class _Seen:
    """Stands in for a traced Observation: record_behaviour only needs its payload."""

    def __init__(self, run: SkillBehaviourPayload) -> None:
        self.skill_id = run.skill_id
        self._run = run

    def payload(self) -> SkillBehaviourPayload:
        return self._run


def _corpus_skill(skill_id: str = "word-count") -> Any:
    return next(s for s in discover_skills(default_root()) if s.skill_id == skill_id)


def test_record_behaviour_scores_each_run(tmp_path: Path) -> None:
    skill = _corpus_skill()
    with BaselineStore(tmp_path / "s.sqlite") as store:
        for n in range(WARMUP):
            seen = cast(Observation, _Seen(_run(n, skill_id=skill.skill_id)))
            recorded = record_behaviour(store, skill, seen, ts=TS)
            assert recorded.alert is None and recorded.score_error is None
        attack = cast(Observation, _Seen(_run(99, skill_id=skill.skill_id, egress=(PUBLIC_443,))))
        recorded = record_behaviour(store, skill, attack, ts=TS)
        assert recorded.alert is not None
        assert recorded.alert.observation_record_id == recorded.record_id
        assert store.verify_chain().ok


def test_a_scorer_fault_keeps_the_run_and_leaves_a_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test report M4: scoring fails open, and says so in the store."""

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("scorer broke")

    monkeypatch.setattr(collector, "score_run", broken)
    skill = _corpus_skill()
    with BaselineStore(tmp_path / "s.sqlite") as store:
        seen = cast(Observation, _Seen(_run(1, skill_id=skill.skill_id)))
        recorded = record_behaviour(store, skill, seen, ts=TS)
        kinds = [r.kind for r in store.read_records()]
        alerts = _alerts(store)
        assert store.verify_chain().ok
    assert recorded.score_error == "RuntimeError: scorer broke"
    assert kinds.count("behaviour") == 1
    assert alerts == [
        {
            "code": FAILED_CODE,
            "reason": "behaviour_score_failed",
            "skill_id": skill.skill_id,
            "observation_record_id": recorded.record_id,
            "detail": "RuntimeError: scorer broke",
        }
    ]
