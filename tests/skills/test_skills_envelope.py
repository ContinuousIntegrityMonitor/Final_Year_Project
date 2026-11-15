"""Per-skill behavioural profile (T-15, feature half)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cim.common.schema.skills import Egress, SkillBehaviourPayload
from cim.common.store import BaselineStore
from cim.skills.__main__ import main
from cim.skills.collector import observe, record_behaviour
from cim.skills.corpus import default_root, load_manifest
from cim.skills.envelope import WARMUP, WINDOW, Numeric, build_profile, profiles
from cim.skills.inventory import append_event
from cim.skills.runner import discover_skills

TS = "2026-11-15T10:00:00Z"


def invocation(
    n: int,
    skill_id: str = "alpha",
    binaries: tuple[str, ...] = ("/usr/bin/bash",),
    writes: tuple[str, ...] = (),
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
        duration_us=1000 + n,
    )


def test_support_sets_count_invocations_and_numbers_are_exact() -> None:
    history = [
        invocation(1, binaries=("/usr/bin/bash", "/usr/bin/sort"), writes=("~",), processes=2),
        invocation(2, binaries=("/usr/bin/bash",), processes=1),
        invocation(
            3,
            binaries=("/usr/bin/bash", "/usr/bin/sort", "/usr/bin/sort"),
            writes=("~", "/tmp"),
            egress=(Egress(dest_class="private_ip", port=9),),
            processes=3,
        ),
    ]
    profile = build_profile("alpha", history)
    assert profile.observations == 3
    assert not profile.warmed_up
    assert profile.binaries == (("/usr/bin/bash", 3), ("/usr/bin/sort", 2))
    assert profile.write_targets == (("/tmp", 1), ("~", 2))
    assert profile.destinations == (("private_ip:9", 1),)
    assert profile.processes == Numeric(count=3, total=6, total_squares=14, minimum=1, maximum=3)
    assert profile.binaries_per_invocation == Numeric(3, 5, 9, 1, 2)
    assert profile.writes_per_invocation == Numeric(3, 3, 5, 0, 2)
    assert profile.destinations_per_invocation == Numeric(3, 1, 1, 0, 1)
    assert profile.duration_us == Numeric(3, 3006, 3012014, 1001, 1003)


def test_warm_up_and_window() -> None:
    history = [invocation(n) for n in range(WARMUP - 1)]
    assert not build_profile("alpha", history).warmed_up
    history.append(invocation(WARMUP))
    assert build_profile("alpha", history).warmed_up
    # Only the last WINDOW invocations count: an old habit ages out.
    old = [invocation(n, binaries=("/usr/bin/old",)) for n in range(5)]
    recent = [invocation(100 + n) for n in range(WINDOW)]
    profile = build_profile("alpha", old + recent)
    assert profile.observations == WINDOW
    assert profile.binaries == (("/usr/bin/bash", WINDOW),)


def test_empty_history_and_render() -> None:
    empty = build_profile("alpha", [])
    assert empty.observations == 0
    assert empty.processes == Numeric(0, 0, 0, 0, 0)
    assert empty.render() == (
        f"alpha: warming_up 0/{WARMUP} window=0 processes=0 binaries=- writes=- destinations=-"
    )
    warmed = build_profile("alpha", [invocation(n, processes=1 + n % 2) for n in range(WARMUP)])
    assert warmed.render() == (
        f"alpha: warmed_up window={WARMUP} processes=1-2 "
        "binaries=/usr/bin/bash writes=- destinations=-"
    )


def test_profiles_read_only_skill_behaviour_from_the_store(tmp_path: Path) -> None:
    with BaselineStore(tmp_path / "store.sqlite") as store:
        alpha = store.append_artefact("skill", "alpha", "lab")
        beta = store.append_artefact("skill", "beta", "lab")
        tool = store.append_artefact("mcp_tool", "nmap_scan", "lab")
        for n in range(3):
            append_event(store, alpha, "behaviour", invocation(n), TS)
        append_event(store, beta, "behaviour", invocation(9, "beta", writes=("~",)), TS)
        # An MCP tool call and a malformed skills record share the store and are skipped.
        store.append_record(
            tool, "behaviour", {"server_id": "hexstrike", "tool_id": "nmap_scan"}, TS
        )
        store.append_record(alpha, "behaviour", {"skill_id": "alpha", "unexpected": 1}, TS)
        before = len(store.read_records())
        found = profiles(store)
        assert [(p.skill_id, p.observations) for p in found] == [("alpha", 3), ("beta", 1)]
        assert profiles(store, "beta") == [found[1]]
        assert profiles(store, "missing") == []
        assert profiles(store) == found  # same records, same profiles
        assert len(store.read_records()) == before  # reading a profile writes nothing


@pytest.mark.usefixtures("needs_tracer")
def test_benign_corpus_gives_the_same_profiles_on_three_consecutive_runs(tmp_path: Path) -> None:
    corpus = default_root()
    manifest = load_manifest(corpus)
    skills = {skill.skill_id: skill for skill in discover_skills(corpus)}
    benign = sorted(skill_id for skill_id, entry in manifest.items() if entry.label == "benign")
    runs = []
    for attempt in range(3):
        with BaselineStore(tmp_path / f"run{attempt}.sqlite") as store:
            for _repeat in range(2):
                for skill_id in benign:
                    run = manifest[skill_id].runs[0]
                    seen = observe(skills[skill_id], skills[skill_id].path / run.script, run.args)
                    record_behaviour(store, skills[skill_id], seen, ts=TS)
            runs.append([profile.stable() for profile in profiles(store)])
    assert [profile["skill_id"] for profile in runs[0]] == benign
    assert all(profile["observations"] == 2 for profile in runs[0])
    assert runs[0] == runs[1] == runs[2]
    # Stable inside one run as well: both invocations of a skill showed the same things.
    for profile in runs[0]:
        assert all(count == 2 for _value, count in profile["binaries"]), profile["skill_id"]
        assert profile["processes"].minimum == profile["processes"].maximum, profile["skill_id"]


@pytest.mark.usefixtures("needs_tracer")
def test_command_line_envelope(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(tmp_path / "store.sqlite")
    assert main(["envelope", "--db", db]) == 2
    assert "no behaviour records" in capsys.readouterr().out
    assert main(["observe", "--db", db, "--skill", "notes-sync", "--skill", "word-count"]) == 0
    capsys.readouterr()
    assert main(["envelope", "--db", db]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith(f"notes-sync: warming_up 1/{WARMUP} window=1 processes=1 ")
    assert lines[0].endswith("writes=- destinations=private_ip:9")
    assert lines[1].endswith("writes=- destinations=-")
    assert main(["envelope", "--db", db, "--skill", "word-count"]) == 0
    assert capsys.readouterr().out.count("\n") == 1
