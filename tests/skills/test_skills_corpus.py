"""Seed corpus (T-05): manifest verifies, every corpus skill runs, membership is observable."""

from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path

import pytest

from cim.skills.__main__ import main
from cim.skills.corpus import (
    UNLABELLED,
    default_root,
    load_manifest,
    run_corpus,
    update_manifest,
    verify_manifest,
)

CORPUS = default_root()


@pytest.fixture
def corpus_copy(tmp_path: Path) -> Path:
    return Path(shutil.copytree(CORPUS, tmp_path / "corpus"))


def test_committed_manifest_verifies() -> None:
    assert verify_manifest(CORPUS) == []


def test_corpus_has_ten_benign_and_three_suspicious_skills() -> None:
    manifest = load_manifest(CORPUS)
    labels = Counter(skill.label for skill in manifest.values())
    assert labels["benign"] >= 10
    assert labels["suspicious"] >= 3
    assert set(labels) == {"benign", "suspicious"}
    assert all(skill.note for skill in manifest.values() if skill.label == "suspicious")


def test_one_byte_edit_is_reported_for_exactly_that_file(corpus_copy: Path) -> None:
    with (corpus_copy / "word-count" / "sample.txt").open("ab") as handle:
        handle.write(b"x")
    assert verify_manifest(corpus_copy) == ["word-count: modified file sample.txt"]


def test_added_and_removed_files_are_reported(corpus_copy: Path) -> None:
    (corpus_copy / "dir-tree" / "scripts" / "extra.sh").write_text("echo extra\n", encoding="utf-8")
    (corpus_copy / "archive-pack" / "docs" / "notes.txt").unlink()
    assert verify_manifest(corpus_copy) == [
        "archive-pack: missing file docs/notes.txt",
        "dir-tree: helper scripts/extra.sh has no scripted run",
        "dir-tree: unexpected file scripts/extra.sh",
    ]


def test_added_and_removed_skills_are_reported(corpus_copy: Path) -> None:
    shutil.rmtree(corpus_copy / "unit-convert")
    planted = corpus_copy / "planted"
    planted.mkdir()
    (planted / "SKILL.md").write_text("---\nname: planted\n---\n", encoding="utf-8")
    assert verify_manifest(corpus_copy) == [
        "planted: on disk but not in the manifest",
        "unit-convert: in the manifest but not on disk",
    ]


def test_update_refreshes_checksums_and_keeps_hand_written_fields(corpus_copy: Path) -> None:
    before = load_manifest(corpus_copy)
    (corpus_copy / "word-count" / "sample.txt").write_text("changed\n", encoding="utf-8")
    assert update_manifest(corpus_copy) == []
    after = load_manifest(corpus_copy)
    assert verify_manifest(corpus_copy) == []
    assert after["word-count"].tree_digest != before["word-count"].tree_digest
    assert after["notes-sync"] == before["notes-sync"]  # label, note, runs and digests


def test_new_skill_must_be_labelled_by_hand(corpus_copy: Path) -> None:
    new = corpus_copy / "newcomer"
    (new / "scripts").mkdir(parents=True)
    (new / "SKILL.md").write_text("---\nname: newcomer\n---\n", encoding="utf-8")
    (new / "scripts" / "go.sh").write_text("echo go\n", encoding="utf-8")
    assert update_manifest(corpus_copy) == ["newcomer"]
    assert load_manifest(corpus_copy)["newcomer"].label == UNLABELLED
    assert verify_manifest(corpus_copy) == ["newcomer: label must be one of benign, suspicious"]


def test_runner_executes_every_corpus_skill() -> None:
    results = run_corpus(CORPUS)
    assert {r.skill_id for r in results} == set(load_manifest(CORPUS))
    assert [
        (r.skill_id, r.result.returncode, r.result.stderr) for r in results if r.result.returncode
    ] == []
    stdout = {r.skill_id: r.result.stdout for r in results}
    assert stdout["unit-convert"] == "12 km = 12000 m\n"
    assert stdout["text-slugify"] == "hello-world-from-cim\n"
    assert stdout["dep-installer"] == "dependencies ok\n"
    assert verify_manifest(CORPUS) == []  # no helper wrote into the corpus


@pytest.mark.usefixtures("needs_scope")
def test_cgroup_membership_is_observable_for_every_corpus_skill() -> None:
    results = run_corpus(CORPUS, scoped=True)
    assert len(results) == len(load_manifest(CORPUS))
    for outcome in results:
        assert outcome.scoped is not None
        assert outcome.result.returncode == 0, outcome.result.stderr
        assert outcome.scoped.cgroup.name.startswith(f"cim-skill-{outcome.skill_id}-inv-")
        assert outcome.scoped.members, outcome.skill_id
    leaked = {o.skill_id: [m.comm for m in o.scoped.leaked] for o in results if o.scoped}
    assert leaked.pop("cache-warmer") == ["sleep"]  # the process it leaves behind
    assert all(not processes for processes in leaked.values())


def test_command_line_verify_and_run(capsys: pytest.CaptureFixture[str], corpus_copy: Path) -> None:
    assert main(["corpus", "verify", "--root", str(corpus_copy)]) == 0
    assert "manifest verifies" in capsys.readouterr().out
    assert main(["corpus", "run", "--root", str(corpus_copy), "--no-scope"]) == 0
    assert "word-count [benign] scripts/count.py exit=0" in capsys.readouterr().out
    (corpus_copy / "word-count" / "sample.txt").write_text("changed\n", encoding="utf-8")
    assert main(["corpus", "verify", "--root", str(corpus_copy)]) == 1
    assert main(["corpus", "update", "--root", str(corpus_copy)]) == 0
    assert main(["corpus", "verify", "--root", str(corpus_copy)]) == 0
