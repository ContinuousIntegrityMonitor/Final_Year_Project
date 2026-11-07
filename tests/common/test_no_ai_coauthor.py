"""Guard: no commit may credit an AI tool as author or co-author."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_ai_coauthor.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_ai_coauthor", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()


def _record(body: str, author: str = "Hamza", email: str = "h@example.com") -> str:
    fields = ["a" * 40, author, email, "Hamza", "h@example.com", body]
    return str(guard.FIELD_SEP.join(fields) + guard.RECORD_SEP)


def test_clean_history_passes() -> None:
    body = "T-01: scaffold\n\nCo-authored-by: fasih-moin <fasihuddin.moin@gmail.com>\n"
    assert guard.find_violations(_record(body)) == []


@pytest.mark.parametrize(
    "trailer",
    [
        "Co-authored-by: Cursor <cursoragent@cursor.com>",
        "co-authored-by: Copilot <copilot@github.com>",
        "Co-Authored-By: Claude <noreply@anthropic.com>",
    ],
)
def test_ai_trailer_is_rejected(trailer: str) -> None:
    violations = guard.find_violations(_record(f"T-07: inventory\n\n{trailer}\n"))
    assert len(violations) == 1
    assert "co-author" in violations[0].reason


def test_ai_author_identity_is_rejected() -> None:
    record = _record("T-07: inventory\n", author="Cursor Agent", email="cursoragent@cursor.com")
    assert [v.reason.split(" ")[0] for v in guard.find_violations(record)] == ["author"]


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Hamza",
        "GIT_AUTHOR_EMAIL": "h@example.com",
        "GIT_COMMITTER_NAME": "Hamza",
        "GIT_COMMITTER_EMAIL": "h@example.com",
    }
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, input=stdin, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_real_git_history_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _git(tmp_path, "init", "-q")
    tree = _git(tmp_path, "write-tree")
    clean = _git(tmp_path, "commit-tree", tree, stdin="T-01: clean\n")
    bad_msg = "T-02: tainted\n\nCo-authored-by: Cursor <cursoragent@cursor.com>\n"
    bad = _git(tmp_path, "commit-tree", tree, "-p", clean, stdin=bad_msg)
    monkeypatch.chdir(tmp_path)
    assert guard.main(["--rev", clean]) == 0
    assert guard.main(["--rev", bad]) == 1


def test_repository_history_is_clean() -> None:
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    log = guard.git_log("HEAD")
    assert guard.find_violations(log) == []
