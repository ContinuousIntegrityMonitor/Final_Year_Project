"""File and tree digests for a skill directory (T-05 manifest, T-08 inventory)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from cim.common.schema.canonical import canonical_json
from cim.skills.digest import UNREADABLE_SHA256, hash_files, tree_digest


def make_tree(root: Path) -> Path:
    skill = root / "alpha"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: alpha\n---\n", encoding="utf-8")
    (skill / "scripts" / "run.sh").write_text("echo hi\n", encoding="utf-8")
    (skill / "data.bin").write_bytes(b"\x00\x01\x02")
    return skill


def test_every_file_is_listed_with_its_digest_and_size(tmp_path: Path) -> None:
    skill = make_tree(tmp_path)
    files = hash_files(skill)
    assert [item.path for item in files] == ["SKILL.md", "data.bin", "scripts/run.sh"]
    assert files[1].sha256 == hashlib.sha256(b"\x00\x01\x02").hexdigest()
    assert files[1].size_bytes == 3


def test_tree_digest_is_stable_and_moves_on_any_change(tmp_path: Path) -> None:
    skill = make_tree(tmp_path)
    before = tree_digest(hash_files(skill))
    assert tree_digest(hash_files(skill)) == before
    (skill / "data.bin").write_bytes(b"\x00\x01\x03")  # one byte
    edited = tree_digest(hash_files(skill))
    (skill / "scripts" / "extra").write_text("#!/bin/sh\n", encoding="utf-8")  # no suffix
    added = tree_digest(hash_files(skill))
    assert len({before, edited, added}) == 3


def test_symlinks_are_recorded_but_never_followed(tmp_path: Path) -> None:
    skill = make_tree(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("one", encoding="utf-8")
    (skill / "link.txt").symlink_to(outside / "secret.txt")
    (skill / "linked-dir").symlink_to(outside)
    first = {item.path: item for item in hash_files(skill)}
    assert {"link.txt", "linked-dir"} <= first.keys()
    assert "linked-dir/secret.txt" not in first
    (outside / "secret.txt").write_text("two", encoding="utf-8")
    assert {item.path: item for item in hash_files(skill)} == first  # target content ignored
    (skill / "link.txt").unlink()
    (skill / "link.txt").symlink_to("/etc/hostname")
    assert hash_files(skill) != list(first.values())  # retargeting is a change


def test_file_name_that_is_not_utf8_stays_hashable(tmp_path: Path) -> None:
    skill = make_tree(tmp_path)
    with open(os.path.join(os.fsencode(skill), b"bad\xffname.sh"), "wb") as handle:
        handle.write(b"echo hi\n")
    files = hash_files(skill)
    assert "bad\\xffname.sh" in [item.path for item in files]
    canonical_json([item.model_dump(mode="json") for item in files]).encode("utf-8")
    assert len(tree_digest(files)) == 64


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read every file")
def test_unreadable_file_is_recorded_not_dropped(tmp_path: Path) -> None:
    skill = make_tree(tmp_path)
    readable = tree_digest(hash_files(skill))
    (skill / "data.bin").chmod(0o000)
    try:
        files = {item.path: item for item in hash_files(skill)}
    finally:
        (skill / "data.bin").chmod(0o644)
    assert files["data.bin"].sha256 == UNREADABLE_SHA256
    assert tree_digest(list(files.values())) != readable
