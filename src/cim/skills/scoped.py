"""Run helper scripts inside one systemd user scope (cgroup v2) per invocation (T-05).

Every process a helper starts, including double-forked grandchildren, stays in the scope's
cgroup. That membership is how later tasks (T-11) attribute behaviour to a skill.
Membership is *sampled* while the helper runs, so a helper shorter than the poll interval
can be missed; T-11 needs a stronger mechanism for that case.
"""

from __future__ import annotations

import functools
import re
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from cim.skills.runner import RunResult, Skill

CGROUP_ROOT = Path("/sys/fs/cgroup")
CLEAN_PATH = "/usr/bin:/bin"
POLL_INTERVAL_S = 0.02
TIMEOUT_RETURNCODE = 124
MAX_OUTPUT_CHARS = 1_000_000


@dataclass(frozen=True)
class Member:
    """One process observed inside an invocation's cgroup."""

    pid: int
    comm: str


@dataclass(frozen=True)
class ScopedRunResult:
    """A helper run plus what its cgroup contained."""

    result: RunResult
    unit: str
    cgroup: Path | None
    members: tuple[Member, ...]  # every process seen while the helper ran
    leaked: tuple[Member, ...]  # still alive after the main script exited (then killed)


@functools.cache
def scope_available() -> bool:
    """True if this session can create transient user scopes (needs a user systemd session)."""
    try:
        proc = subprocess.run(
            ["systemd-run", "--user", "--scope", "--quiet", "true"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def new_invocation_id() -> str:
    return f"inv-{uuid.uuid4().hex[:12]}"


def scope_unit_name(skill_id: str, invocation_id: str) -> str:
    """systemd-safe unit name (without the .scope suffix) for one invocation."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", skill_id)
    return f"cim-skill-{safe}-{invocation_id}"


def cgroup_path_from_proc(text: str) -> Path | None:
    """Extract the cgroup v2 path from /proc/<pid>/cgroup content ('0::/some/path')."""
    for line in text.splitlines():
        hierarchy, _, rest = line.partition(":")
        if hierarchy == "0":
            _, _, path = rest.partition(":")
            return CGROUP_ROOT / path.lstrip("/")
    return None


def _own_scope(pid: int, unit: str) -> Path | None:
    try:
        text = Path(f"/proc/{pid}/cgroup").read_text()
    except OSError:
        return None
    path = cgroup_path_from_proc(text)
    if path is not None and path.name == f"{unit}.scope":
        return path
    return None


def _read_members(cgroup: Path) -> list[Member]:
    try:
        pids = [int(p) for p in (cgroup / "cgroup.procs").read_text().split()]
    except OSError:
        return []
    members: list[Member] = []
    for pid in pids:
        try:
            comm = Path(f"/proc/{pid}/comm").read_text().strip()
        except OSError:
            continue
        members.append(Member(pid, comm))
    return members


def _kill_scope(cgroup: Path | None, proc: subprocess.Popen[str]) -> None:
    if cgroup is not None:
        try:
            (cgroup / "cgroup.kill").write_text("1")
            return
        except OSError:
            pass
    proc.kill()


def run_script_scoped(
    skill: Skill,
    script: Path,
    args: tuple[str, ...] = (),
    timeout: float = 30.0,
    invocation_id: str | None = None,
) -> ScopedRunResult:
    """Run one helper in its own systemd user scope with a clean environment.

    The environment is cleaned *inside* the scope (env -i): systemd-run itself needs the
    caller's XDG_RUNTIME_DIR to reach the user session. Call scope_available() first.
    """
    script = script.resolve()
    if script.suffix == ".py":
        inner = [sys.executable, str(script), *args]
    elif script.suffix == ".sh":
        inner = ["bash", str(script), *args]
    else:
        raise ValueError(f"unsupported helper script type: {script.name}")

    invocation = invocation_id or new_invocation_id()
    unit = scope_unit_name(skill.skill_id, invocation)
    seen: dict[int, Member] = {}
    cgroup: Path | None = None
    timed_out = False

    with (
        tempfile.TemporaryDirectory(prefix="cim-skill-") as home,
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as out_f,
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as err_f,
    ):
        cmd = [
            "systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "--",
            "env", "-i", f"PATH={CLEAN_PATH}", f"HOME={home}", "LANG=C.UTF-8", *inner,
        ]  # fmt: skip
        proc = subprocess.Popen(
            cmd,
            cwd=skill.path,
            stdin=subprocess.DEVNULL,
            stdout=out_f,
            stderr=err_f,
            text=True,
        )
        deadline = time.monotonic() + timeout
        while True:
            if cgroup is None:
                cgroup = _own_scope(proc.pid, unit)
            if cgroup is not None:
                for member in _read_members(cgroup):
                    seen[member.pid] = member
            try:
                proc.wait(timeout=POLL_INTERVAL_S)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    timed_out = True
                    _kill_scope(cgroup, proc)
                    proc.wait()
                    break

        leaked: tuple[Member, ...] = ()
        if cgroup is not None and cgroup.exists():
            leaked = tuple(_read_members(cgroup))
            for member in leaked:
                seen[member.pid] = member
            if leaked:
                _kill_scope(cgroup, proc)

        out_f.seek(0)
        err_f.seek(0)
        stdout = out_f.read(MAX_OUTPUT_CHARS)
        stderr = err_f.read(MAX_OUTPUT_CHARS)

    returncode = TIMEOUT_RETURNCODE if timed_out else int(proc.returncode)
    if timed_out:
        stderr += f"timeout after {timeout}s"
    result = RunResult(skill.skill_id, script, returncode, stdout, stderr)
    members = tuple(sorted(seen.values(), key=lambda m: m.pid))
    return ScopedRunResult(result, unit, cgroup, members, leaked)
