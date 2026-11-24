"""File and tree digests for one skill directory (T-05 corpus manifest, T-08 inventory).

Every entry under the skill root is hashed, not only SKILL.md and the helper scripts: a new
data file or an extension-less executable changes what a skill can do just as a new .py does.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from cim.common.schema.canonical import canonical_json
from cim.common.schema.skills import SkillFile

UNREADABLE_SHA256 = "0" * 64  # recorded for a file that exists but cannot be read
_CHUNK = 1 << 20


def record_path(relative: str) -> str:
    """A relative path as it is written into records: always valid UTF-8, always ``/``.

    File names are bytes on Linux. Bytes that are not UTF-8 are written as \\xNN, so an
    oddly named file cannot make a record unhashable. Separators are normalised to ``/``
    so the same skill tree hashes the same on Windows and Linux (manifest verify).
    """
    normalised = relative.replace("\\", "/")
    return os.fsencode(normalised).decode("utf-8", errors="backslashreplace")


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _entry(path: str, relative: str) -> SkillFile | None:
    try:
        if os.path.islink(path):
            # Never follow links out of the skill; record where the link points instead.
            target = os.fsencode(os.readlink(path))
            return SkillFile(
                path=record_path(relative),
                sha256=hashlib.sha256(b"symlink:" + target).hexdigest(),
                size_bytes=len(target),
            )
        if not os.path.isfile(path):
            return None  # fifo, socket, device
        size = os.lstat(path).st_size
    except OSError:
        return None  # vanished while we were looking
    try:
        sha256 = _file_sha256(path)
    except OSError:
        sha256 = UNREADABLE_SHA256
    return SkillFile(path=record_path(relative), sha256=sha256, size_bytes=size)


def hash_files(skill_dir: Path) -> list[SkillFile]:
    """One SkillFile per file or symlink under skill_dir, sorted by path."""
    root = os.fspath(skill_dir)
    files: list[SkillFile] = []
    for directory, dirnames, filenames in os.walk(root):
        linked_dirs = [name for name in dirnames if os.path.islink(os.path.join(directory, name))]
        for name in [*filenames, *linked_dirs]:
            path = os.path.join(directory, name)
            entry = _entry(path, os.path.relpath(path, root))
            if entry is not None:
                files.append(entry)
    return sorted(files, key=lambda item: item.path)


def tree_digest(files: list[SkillFile]) -> str:
    """One digest for a whole skill: changes when any file is added, removed or edited."""
    listing = [item.model_dump(mode="json") for item in sorted(files, key=lambda f: f.path)]
    return hashlib.sha256(canonical_json(listing).encode("utf-8")).hexdigest()
