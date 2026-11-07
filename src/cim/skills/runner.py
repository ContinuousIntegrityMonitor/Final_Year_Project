"""Minimal skill runner: discover skills, parse SKILL.md, run helper scripts (T-05)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

HELPER_SUFFIXES = {".py", ".sh"}


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


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse simple `key: value` lines between the leading `---` markers."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return meta
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip("\"'")
    return {}


def discover_skills(root: Path) -> list[Skill]:
    """Return every directory under root that contains a SKILL.md."""
    skills: list[Skill] = []
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        manifest = skill_dir / "SKILL.md"
        if not manifest.is_file():
            continue
        meta = parse_frontmatter(manifest.read_text(encoding="utf-8"))
        helpers = tuple(
            sorted(p for p in skill_dir.rglob("*") if p.is_file() and p.suffix in HELPER_SUFFIXES)
        )
        skills.append(
            Skill(
                skill_id=skill_dir.name,
                path=skill_dir,
                name=meta.get("name", skill_dir.name),
                description=meta.get("description", ""),
                helper_scripts=helpers,
            )
        )
    return skills


def run_script(
    skill: Skill,
    script: Path,
    args: tuple[str, ...] = (),
    timeout: float = 30.0,
) -> RunResult:
    """Run one helper script with a clean environment and scripted arguments."""
    if script.suffix == ".py":
        cmd = [sys.executable, str(script), *args]
    elif script.suffix == ".sh":
        cmd = ["bash", str(script), *args]
    else:
        raise ValueError(f"unsupported helper script type: {script.name}")
    with tempfile.TemporaryDirectory(prefix="cim-skill-") as home:
        env = {"PATH": "/usr/bin:/bin", "HOME": home, "LANG": "C.UTF-8"}
        try:
            proc = subprocess.run(
                cmd,
                cwd=skill.path,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return RunResult(skill.skill_id, script, 124, "", f"timeout after {timeout}s")
    return RunResult(skill.skill_id, script, proc.returncode, proc.stdout, proc.stderr)
