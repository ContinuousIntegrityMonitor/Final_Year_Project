"""Skills half of the T-17 attack pack: A3 trigger payload, A4 legitimate update."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from cim.common.schema.skills import Egress, SkillBehaviourPayload
from cim.common.store import BaselineStore
from cim.skills.__main__ import main
from cim.skills.attacks import (
    A3_INPUT,
    A3_SKILL,
    A4_SKILL,
    A4_UPDATE,
    ATTACKS_DIRNAME,
    local_listener,
    novel_values,
    prepare,
    run_a3,
    run_a4,
)
from cim.skills.board import skills_board
from cim.skills.corpus import default_root, load_manifest, verify_manifest
from cim.skills.envelope import build_profile
from cim.skills.runner import discover_skills

CORPUS = default_root()
BRIEF = CORPUS / A3_SKILL / "scripts" / "brief.py"


def payload(n: int, *, binaries: tuple[str, ...] = ("/usr/bin/python3",), port: int = 0):
    return SkillBehaviourPayload(
        skill_id="s",
        invocation_id=f"inv-{n}",
        cgroup_id=f"scope-{n}",
        binaries_executed=list(binaries),
        file_write_targets=[],
        egress=[Egress(dest_class="private_ip", port=port)] if port else [],
        process_count=1,
        duration_us=1,
    )


def test_attack_inputs_are_not_skills_and_the_corpus_still_verifies() -> None:
    names = {skill.skill_id for skill in discover_skills(CORPUS)}
    assert ATTACKS_DIRNAME not in names and A3_SKILL in names
    assert (CORPUS / ATTACKS_DIRNAME / A3_INPUT).is_file()
    assert (CORPUS / ATTACKS_DIRNAME / A4_UPDATE / "SKILL.md").is_file()
    assert verify_manifest(CORPUS) == []
    entry = load_manifest(CORPUS)[A3_SKILL]
    assert entry.label == "suspicious" and entry.note
    assert [run.args for run in entry.runs] == [("notes.md",)]  # the scripted run is benign


def test_trigger_skill_is_quiet_without_the_trigger_word() -> None:
    with local_listener() as (port, received):
        done = subprocess.run(
            [sys.executable, str(BRIEF), "notes.md", "--port", str(port)],
            cwd=BRIEF.parent.parent,
            capture_output=True,
            text=True,
            check=True,
        )
        # Nothing connects, so end the listener's wait by connecting once ourselves.
        socket.create_connection(("127.0.0.1", port)).close()
    assert done.stdout.startswith("brief: 4 action points")
    assert bytes(received) == b""


def test_trigger_sends_variable_names_never_values(tmp_path: Path) -> None:
    trigger = CORPUS / ATTACKS_DIRNAME / A3_INPUT
    env = {"PATH": "/usr/bin:/bin", "LAB_SECRET": "do-not-send-this-value"}
    with local_listener() as (port, received):
        subprocess.run(
            [sys.executable, str(BRIEF), str(trigger), "--port", str(port)],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            check=True,
        )
    message = json.loads(bytes(received))
    assert "LAB_SECRET" in message["env_names"]
    assert b"do-not-send-this-value" not in received and b"/usr/bin" not in received
    assert message["decoy"].startswith("CIM-LAB-DECOY")


def test_novel_values_is_the_never_seen_check() -> None:
    profile = build_profile("s", [payload(n) for n in range(30)])
    assert novel_values(profile, payload(31)) == []
    assert novel_values(profile, payload(31, port=443)) == ["destinations: private_ip:443"]
    assert novel_values(profile, payload(31, binaries=("/usr/bin/python3", "/usr/bin/curl"))) == [
        "binaries: /usr/bin/curl"
    ]


def test_prepare_refuses_a_used_directory(tmp_path: Path) -> None:
    (tmp_path / "left-over").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        prepare(tmp_path, CORPUS)


def test_a3_alerts_on_behaviour_while_the_files_stay_the_same(
    needs_tracer: None, tmp_path: Path
) -> None:
    root = prepare(tmp_path / "work", CORPUS)
    with BaselineStore(tmp_path / "store.sqlite") as store:
        report = run_a3(store, root, warmup=30)
    assert report.passed
    assert report.changes == () and report.digest_before == report.digest_after
    assert report.profile.destinations == ()  # the benign runs never connect
    assert len(report.run.egress) == 1 and report.run.egress[0].dest_class == "private_ip"
    assert report.novel == (f"destinations: private_ip:{report.run.egress[0].port}",)
    # T-16: the scorer wrote a real alert for the attack run, naming the new destination.
    assert report.alert is not None and report.alert.code == "skill_behaviour_drift"
    assert report.alert.features[0].feature == "destinations"
    assert report.alert.features[0].values == [f"private_ip:{report.run.egress[0].port}"]
    with BaselineStore(tmp_path / "store.sqlite") as store:
        board = skills_board(store.read_records())
        assert store.verify_chain().ok
    assert [(a.skill_id, a.code) for a in board.alerts] == [(A3_SKILL, "skill_behaviour_drift")]
    assert report.received is not None and b"CIM-LAB-DECOY" in report.received
    assert verify_manifest(CORPUS) == []  # the corpus itself was not touched


def test_a4_update_is_a_file_change_and_not_a_behaviour_change(
    needs_tracer: None, tmp_path: Path
) -> None:
    root = prepare(tmp_path / "work", CORPUS)
    with BaselineStore(tmp_path / "store.sqlite") as store:
        report = run_a4(store, root, warmup=30)
    assert report.passed
    assert [(c.change, c.path) for c in report.changes] == [
        ("modify", "SKILL.md"),
        ("modify", "scripts/count.py"),
    ]
    assert report.digest_before != report.digest_after
    assert report.novel == ()
    assert report.alert is None  # a legitimate update: no behaviour alert
    assert verify_manifest(CORPUS) == []
    assert (CORPUS / A4_SKILL / "scripts" / "count.py").read_text(encoding="utf-8").count(
        "longest"
    ) == 0  # the update went to the copy only


def test_cli_runs_an_attack(
    needs_tracer: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["attack", "A3", "--work", str(tmp_path / "w"), "--warmup", "30"]) == 0
    out = capsys.readouterr().out
    assert "attack A3: sweep recorded no file change" in out
    assert "attack A3: tree digest unchanged" in out
    assert out.count(": PASS") == 1
    assert "attack A3: behaviour alert: meeting-brief changed how it behaves: destinations" in out
    with pytest.raises(SystemExit, match="not empty"):
        main(["attack", "A3", "--work", str(tmp_path / "w")])
