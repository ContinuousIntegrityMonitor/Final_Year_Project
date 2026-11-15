"""Minimal skill runner: discover skills, parse SKILL.md, run helper scripts (T-05)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO

HELPER_SUFFIXES = {".py", ".sh"}
CLEAN_PATH = "/usr/bin:/bin"
TIMEOUT_RETURNCODE = 124
MAX_OUTPUT_BYTES = 1_000_000
_BLOCK_JOINERS = {">": " ", "|": "\n"}  # YAML folded / literal block scalars


@dataclass(frozen=True)
class Skill:
    """One installed skill directory."""

    skill_id: str
    path: Path
    name: str
    description: str
    helper_scripts: tuple[Path, ...]


@dataclass(frozen=True)
class RunResult:
    """Outcome of one helper-script invocation."""

    skill_id: str
    script: Path
    returncode: int
    stdout: str
    stderr: str


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse top-level `key: value` pairs between the leading `---` markers.

    Covers what SKILL.md files use: plain and quoted scalars, block scalars (`>`, `|`) and
    indented continuation lines. Nested mappings and lists are skipped. Not a YAML parser.
    """
    lines = text.removeprefix("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    open_key = ""  # key whose value continues on the indented lines that follow
    joiner = " "
    for line in lines[1:]:
        if line.strip() == "---":
            return {key: _unquote(value) for key, value in meta.items()}
        if line.startswith((" ", "\t")):
            part = line.strip()
            if open_key and part:
                meta[open_key] = f"{meta[open_key]}{joiner}{part}" if meta[open_key] else part
            continue
        open_key = ""
        if ":" not in line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value[:1] in _BLOCK_JOINERS and value[1:] in ("", "-", "+"):
            meta[key], open_key, joiner = "", key, _BLOCK_JOINERS[value[0]]
        else:
            meta[key] = value
            if value:  # an empty value followed by indented lines is a nested structure
                open_key, joiner = key, " "
    return {}


def discover_skills(root: Path) -> list[Skill]:
    """Return every direct child directory of root that contains a SKILL.md."""
    skills: list[Skill] = []
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        manifest = skill_dir / "SKILL.md"
        if not manifest.is_file():
            continue
        # One undecodable SKILL.md must not hide every other skill from the monitor.
        meta = parse_frontmatter(manifest.read_text(encoding="utf-8", errors="replace"))
        helpers = tuple(
            sorted(p for p in skill_dir.rglob("*") if p.is_file() and p.suffix in HELPER_SUFFIXES)
        )
        skills.append(
            Skill(
                skill_id=skill_dir.name,
                path=skill_dir,
                name=meta.get("name") or skill_dir.name,
                description=meta.get("description", ""),
                helper_scripts=helpers,
            )
        )
    return skills


def helper_command(script: Path, args: tuple[str, ...] = ()) -> list[str]:
    """Interpreter command line for one helper.

    The script path is made absolute because the helper runs with the skill directory as its
    working directory, where a path relative to the caller would not resolve.
    """
    path = str(script.resolve())
    if script.suffix == ".py":
        return [sys.executable, path, *args]
    if script.suffix == ".sh":
        return ["bash", path, *args]
    raise ValueError(f"unsupported helper script type: {script.name}")


def clean_env(home: str) -> dict[str, str]:
    """The only variables a helper sees.

    PYTHONDONTWRITEBYTECODE keeps Python from writing .pyc files. Otherwise the first run on
    a machine writes into the interpreter's own directories and into the skill, and later
    runs do not: the same helper would look different from one run to the next.
    """
    return {
        "PATH": CLEAN_PATH,
        "HOME": home,
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def read_output(stream: IO[bytes]) -> str:
    """First MAX_OUTPUT_BYTES of captured output. Helper output is untrusted: bytes that are
    not UTF-8 become U+FFFD instead of raising."""
    stream.seek(0)
    return stream.read(MAX_OUTPUT_BYTES).decode("utf-8", errors="replace")


def with_timeout_note(stderr: str, timeout: float) -> str:
    separator = "" if not stderr or stderr.endswith("\n") else "\n"
    return f"{stderr}{separator}timeout after {timeout}s"


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass  # nothing left in the group


def run_script(
    skill: Skill,
    script: Path,
    args: tuple[str, ...] = (),
    timeout: float = 30.0,
) -> RunResult:
    """Run one helper script with a clean environment and scripted arguments.

    The helper leads its own process group. The whole group is killed on timeout and once the
    main script has exited, so background children do not outlive the call. A process that
    leaves the group (setsid, double fork) escapes: run_script_scoped contains those.
    """
    cmd = helper_command(script, args)
    with (
        tempfile.TemporaryDirectory(prefix="cim-skill-", ignore_cleanup_errors=True) as home,
        tempfile.TemporaryFile() as out_f,
        tempfile.TemporaryFile() as err_f,
    ):
        # Output goes to files, not pipes: a background child holding a pipe open would
        # otherwise block the read after the main script is gone.
        proc = subprocess.Popen(
            cmd,
            cwd=skill.path,
            env=clean_env(home),
            stdin=subprocess.DEVNULL,
            stdout=out_f,
            stderr=err_f,
            start_new_session=True,
        )
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            _kill_group(proc.pid)
            proc.wait()
        stdout = read_output(out_f)
        stderr = read_output(err_f)
    if timed_out:
        return RunResult(
            skill.skill_id, script, TIMEOUT_RETURNCODE, stdout, with_timeout_note(stderr, timeout)
        )
    return RunResult(skill.skill_id, script, proc.returncode, stdout, stderr)
