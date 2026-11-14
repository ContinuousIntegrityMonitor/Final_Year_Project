"""Skills artefact inventory and sweep (T-08)."""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from cim.common.schema.envelope import Artefact, Event
from cim.common.store import BaselineStore
from cim.skills.__main__ import main
from cim.skills.corpus import default_root, load_manifest
from cim.skills.inventory import (
    known_skills,
    skill_roots,
    sweep,
    take_inventory,
    write_baselines,
)

TS = "2026-11-15T10:00:00Z"
LATER = "2026-11-15T10:01:00Z"


def make_skill(root: Path, name: str) -> Path:
    skill = root / name
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test skill {name}\n---\n", encoding="utf-8"
    )
    (skill / "scripts" / "run.sh").write_text("echo run\n", encoding="utf-8")
    return skill


@pytest.fixture
def root(tmp_path: Path) -> Path:
    skills = tmp_path / "skills"
    for name in ("alpha", "beta", "gamma"):
        make_skill(skills, name)
    return skills


@pytest.fixture
def store(tmp_path: Path, root: Path) -> Iterator[BaselineStore]:
    with BaselineStore(tmp_path / "store.sqlite") as opened:
        write_baselines(opened, take_inventory([root]), ts=TS)
        yield opened


def records(store: BaselineStore, kind: str) -> list[dict[str, object]]:
    return [json.loads(r.payload) for r in store.read_records() if r.kind == kind]


def summary(store: BaselineStore, root: Path) -> list[tuple[str, str, str]]:
    result = sweep(store, [root], ts=LATER)
    return [(e.skill_id, e.change, e.path) for e in result.events]


def test_n_installed_skills_produce_n_baselines(store: BaselineStore, root: Path) -> None:
    baselines = records(store, "artefact")
    assert [b["skill_id"] for b in baselines] == ["alpha", "beta", "gamma"]
    assert write_baselines(store, take_inventory([root]), ts=LATER) == []  # nothing new
    assert len(records(store, "artefact")) == 3
    assert store.verify_chain().ok


def test_baselines_satisfy_the_event_contract(store: BaselineStore) -> None:
    for payload in records(store, "artefact"):
        skill_id = str(payload["skill_id"])
        Event(
            ts=TS, artefact=Artefact(type="skill", skill=skill_id), kind="artefact", payload=payload
        )
        assert payload["name"] == skill_id
        assert payload["description"] == f"test skill {skill_id}"


def test_unchanged_skills_sweep_clean_and_write_nothing(store: BaselineStore, root: Path) -> None:
    before = len(store.read_records())
    assert sweep(store, [root], ts=LATER) == sweep(store, [root], ts=LATER)
    assert summary(store, root) == []
    assert len(store.read_records()) == before


def test_one_byte_edit_flags_exactly_that_artefact(store: BaselineStore, root: Path) -> None:
    with (root / "beta" / "scripts" / "run.sh").open("ab") as handle:
        handle.write(b"#")
    result = sweep(store, [root], ts=LATER)
    assert [(e.skill_id, e.change, e.path) for e in result.events] == [
        ("beta", "modify", "scripts/run.sh")
    ]
    event = result.events[0]
    assert event.old_sha256 != event.new_sha256
    stored = records(store, "integrity")
    assert stored == [event.model_dump(mode="json")]
    assert store.verify_chain().ok


def test_newly_added_helper_is_caught_on_sweep(store: BaselineStore, root: Path) -> None:
    (root / "alpha" / "scripts" / "extra.py").write_text("print('x')\n", encoding="utf-8")
    (root / "alpha" / "payload").write_text("#!/bin/sh\n", encoding="utf-8")  # no suffix
    assert summary(store, root) == [
        ("alpha", "create", "payload"),
        ("alpha", "create", "scripts/extra.py"),
    ]


def test_a_change_is_reported_once(store: BaselineStore, root: Path) -> None:
    (root / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\nedited\n", encoding="utf-8")
    assert summary(store, root) == [("alpha", "modify", "SKILL.md")]
    assert summary(store, root) == []
    assert len(records(store, "integrity")) == 1
    assert len(records(store, "artefact")) == 3  # the first baseline is never rewritten


def test_delete_and_rename(store: BaselineStore, root: Path) -> None:
    (root / "alpha" / "scripts" / "run.sh").rename(root / "alpha" / "scripts" / "go.sh")
    (root / "gamma" / "scripts" / "run.sh").unlink()
    result = sweep(store, [root], ts=LATER)
    assert [(e.skill_id, e.change, e.path, e.old_path) for e in result.events] == [
        ("alpha", "rename", "scripts/go.sh", "scripts/run.sh"),
        ("gamma", "delete", "scripts/run.sh", None),
    ]
    assert summary(store, root) == []


def test_rename_and_replace_is_caught(store: BaselineStore, root: Path) -> None:
    planted = root / "beta" / "scripts" / "evil.sh"
    planted.write_text("echo evil\n", encoding="utf-8")
    assert summary(store, root) == [("beta", "create", "scripts/evil.sh")]
    planted.rename(root / "beta" / "scripts" / "run.sh")  # replaces the real helper
    assert summary(store, root) == [
        ("beta", "delete", "scripts/evil.sh"),
        ("beta", "modify", "scripts/run.sh"),
    ]


def test_new_and_removed_skills(store: BaselineStore, root: Path) -> None:
    make_skill(root, "delta")
    shutil.rmtree(root / "gamma")
    result = sweep(store, [root], ts=LATER)
    assert result.new_skills == ("delta",)
    assert [(e.skill_id, e.change, e.path) for e in result.events] == [
        ("delta", "create", "SKILL.md"),
        ("delta", "create", "scripts/run.sh"),
        ("gamma", "delete", "SKILL.md"),
        ("gamma", "delete", "scripts/run.sh"),
    ]
    assert summary(store, root) == []
    make_skill(root, "gamma")  # comes back
    assert summary(store, root) == [
        ("gamma", "create", "SKILL.md"),
        ("gamma", "create", "scripts/run.sh"),
    ]
    assert len(records(store, "artefact")) == 4  # alpha, beta, gamma, delta: one each


def test_state_survives_reopening_the_store(
    tmp_path: Path, store: BaselineStore, root: Path
) -> None:
    (root / "alpha" / "scripts" / "run.sh").write_text("echo changed\n", encoding="utf-8")
    assert summary(store, root) == [("alpha", "modify", "scripts/run.sh")]
    store.close()
    with BaselineStore(tmp_path / "store.sqlite") as reopened:
        assert summary(reopened, root) == []
        current = take_inventory([root])["alpha"]
        assert known_skills(reopened)["alpha"].files == {f.path: f.sha256 for f in current.files}


def test_mcp_records_in_the_same_store_are_ignored(store: BaselineStore, root: Path) -> None:
    server = store.append_artefact("mcp_server", "hexstrike", "vm-mon")
    store.append_record(
        server, "artefact", {"code": "mcp_pin", "server_id": "hexstrike", "tools": []}, TS
    )
    store.append_record(
        server, "integrity", {"server_id": "hexstrike", "change": "modify", "path": "x"}, TS
    )
    assert set(known_skills(store)) == {"alpha", "beta", "gamma"}
    assert summary(store, root) == []


def test_same_name_under_two_roots_and_a_missing_root(tmp_path: Path, root: Path) -> None:
    second = tmp_path / "second"
    make_skill(second, "alpha")
    (second / "alpha" / "scripts" / "run.sh").write_text("echo other\n", encoding="utf-8")
    found = take_inventory([root, tmp_path / "does-not-exist", second])
    assert sorted(found) == ["alpha", "alpha#2", "beta", "gamma"]
    assert found["alpha"].tree_digest != found["alpha#2"].tree_digest
    assert found["alpha#2"].root == str(second / "alpha")


def test_skill_roots_come_from_the_environment() -> None:
    env = {"CIM_SKILL_ROOTS": os.pathsep.join(["/opt/skills", "", "/home/u/.claude/skills"])}
    assert skill_roots(env) == [Path("/opt/skills"), Path("/home/u/.claude/skills")]
    assert skill_roots({}) == []


def test_corpus_inventory_matches_the_corpus_manifest(tmp_path: Path) -> None:
    corpus = default_root()
    manifest = load_manifest(corpus)
    with BaselineStore(tmp_path / "corpus.sqlite") as opened:
        written = write_baselines(opened, take_inventory([corpus]), ts=TS)
        assert written == sorted(manifest)
        for payload in records(opened, "artefact"):
            assert payload["tree_digest"] == manifest[str(payload["skill_id"])].tree_digest
        assert opened.verify_chain().ok


def test_command_line_inventory_then_sweep(
    tmp_path: Path, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = str(tmp_path / "cli.sqlite")
    assert main(["inventory", "--db", db, "--root", str(root)]) == 0
    assert "skills=3 new_baselines=3 chain=ok" in capsys.readouterr().out
    assert main(["sweep", "--db", db, "--root", str(root)]) == 0
    assert capsys.readouterr().out == "sweep: unchanged\n"
    (root / "alpha" / "scripts" / "run.sh").rename(root / "alpha" / "scripts" / "go.sh")
    assert main(["sweep", "--db", db, "--root", str(root)]) == 0
    assert capsys.readouterr().out == "sweep: alpha: rename scripts/go.sh (was scripts/run.sh)\n"
