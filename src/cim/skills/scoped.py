"""Run helper scripts inside one systemd user scope (cgroup v2) per invocation (T-05).

Every process a helper starts, including double-forked grandchildren, stays in the scope's
cgroup. That membership is how later tasks (T-11) attribute behaviour to a skill.

The helper is held behind a start gate until its cgroup is known. So the helper's own
process is always recorded, and anything it leaves behind is always found and killed, however
short the helper is. Its children are *sampled* while it runs: a child that lives for less
than the poll interval can still be missed.

Known limit: the scope belongs to the same user as the helper, and systemd delegates that
user's cgroup subtree to them. Sub-cgroups a helper creates *inside* its scope are followed,
but a helper that writes a PID into a cgroup *outside* its scope moves that process out: it
is no longer attributed or killed. T-11 needs a boundary a same-user process cannot cross
(another uid, or audit events) before this holds against a helper that actively evades.
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cim.skills.runner import (
    TIMEOUT_RETURNCODE,
    RunResult,
    Skill,
    clean_env,
    helper_command,
    read_output,
    with_timeout_note,
)

CGROUP_ROOT = Path("/sys/fs/cgroup")
POLL_INTERVAL_S = 0.02
SCOPE_START_TIMEOUT_S = 10.0
SETTLE_TIMEOUT_S = 2.0
MAX_SKILL_ID_CHARS = 100  # a unit name is limited to 255 characters
COMM_MAX = 15  # the kernel truncates /proc/<pid>/comm to this length

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")
_GATE_POLL_S = 0.002
# Wait for one line on stdin, then become the helper. EOF without a line means "do not run".
_GATE = 'IFS= read -r _ && exec "$@" </dev/null'
# What the helper's PID is called while it is still being launched (systemd-run, env, gate).
_LAUNCH_COMMS = frozenset({"systemd-run", "env", "sh"})


class ScopeError(RuntimeError):
    """systemd did not create the scope. The helper never ran."""


class Tracer(Protocol):
    """Something that runs the helper as its child and reports when the helper is done.

    A tracer stays alive for as long as anything it traces is alive, so its own exit cannot
    tell us that the helper's main process has finished. It has to say so itself.
    """

    def command(self, inner: list[str]) -> list[str]:
        """The command line that runs `inner` under the tracer."""
        ...

    def helper_exit(self) -> int | None:
        """The helper's exit status once its main process has finished, else None."""
        ...


@dataclass(frozen=True)
class Member:
    """One process observed inside an invocation's cgroup."""

    pid: int
    comm: str


@dataclass(frozen=True)
class ScopedRunResult:
    """A helper run plus what its cgroup contained."""

    result: RunResult
    invocation_id: str
    unit: str
    cgroup: Path
    home: Path  # the helper's temporary HOME; removed when the run ends
    # The helper itself plus every process sampled in its cgroup. Under a tracer the tracer
    # is left out and the helper is only listed if a sample caught it; the trace is complete.
    members: tuple[Member, ...]
    leaked: tuple[Member, ...]  # outlived the main script (then killed); empty after a timeout


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
    safe_skill = _UNSAFE.sub("_", skill_id)[:MAX_SKILL_ID_CHARS]
    return f"cim-skill-{safe_skill}-{_UNSAFE.sub('_', invocation_id)}"


def cgroup_path_from_proc(text: str) -> Path | None:
    """Extract the cgroup v2 path from /proc/<pid>/cgroup content ('0::/some/path')."""
    for line in text.splitlines():
        hierarchy, _, rest = line.partition(":")
        if hierarchy == "0":
            _, _, path = rest.partition(":")
            return CGROUP_ROOT / path.lstrip("/")
    return None


def _read_proc(path: Path) -> str | None:
    """Read a /proc or cgroup file. A helper controls some of these bytes (its comm, the
    names of cgroups it creates), so nothing here may raise on what it finds."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _own_scope(pid: int, unit: str) -> Path | None:
    text = _read_proc(Path(f"/proc/{pid}/cgroup"))
    path = cgroup_path_from_proc(text) if text is not None else None
    if path is not None and path.name == f"{unit}.scope":
        return path
    return None


def _await_scope(proc: subprocess.Popen[bytes], unit: str) -> Path | None:
    """The scope's cgroup once systemd has moved the gated process into it."""
    deadline = time.monotonic() + SCOPE_START_TIMEOUT_S
    while time.monotonic() < deadline:
        cgroup = _own_scope(proc.pid, unit)
        if cgroup is not None or proc.poll() is not None:
            return cgroup
        time.sleep(_GATE_POLL_S)
    return None


def _open_gate(proc: subprocess.Popen[bytes]) -> None:
    assert proc.stdin is not None
    try:
        proc.stdin.write(b"\n")
        proc.stdin.close()
    except OSError:
        pass  # the gate process is already gone; wait() reports how it ended


def _read_members(cgroup: Path) -> list[Member]:
    """Processes in the cgroup and in every sub-cgroup created beneath it."""
    members: list[Member] = []
    for directory, _dirs, _files in os.walk(cgroup):
        procs = _read_proc(Path(directory, "cgroup.procs"))
        for token in (procs or "").split():
            if not token.isdigit():
                continue
            comm = _read_proc(Path(f"/proc/{token}/comm"))
            if comm is not None:
                members.append(Member(int(token), comm.strip()))
    return members


def _kill_scope(cgroup: Path, unit: str) -> None:
    """SIGKILL everything in the scope, sub-cgroups included."""
    try:
        (cgroup / "cgroup.kill").write_text("1")
        return
    except OSError:
        if not cgroup.exists():
            return  # nothing left to kill
    try:  # kernel older than 5.14 has no cgroup.kill
        subprocess.run(
            ["systemctl", "--user", "kill", "--signal=KILL", f"{unit}.scope"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _wait_empty(cgroup: Path) -> None:
    """Wait until killed members are really gone; the kernel reaps them asynchronously."""
    deadline = time.monotonic() + SETTLE_TIMEOUT_S
    while time.monotonic() < deadline:
        events = _read_proc(cgroup / "cgroup.events")
        if events is None or "populated 0" in events:
            return
        time.sleep(POLL_INTERVAL_S)


def run_script_scoped(
    skill: Skill,
    script: Path,
    args: tuple[str, ...] = (),
    timeout: float = 30.0,
    invocation_id: str | None = None,
    tracer: Tracer | None = None,
) -> ScopedRunResult:
    """Run one helper in its own systemd user scope with a clean environment.

    The environment is cleaned *inside* the scope (env -i): systemd-run itself needs the
    caller's XDG_RUNTIME_DIR to reach the user session. Call scope_available() first.
    Raises ScopeError if the scope cannot be created; the helper has not run in that case.
    The timeout covers the helper only, not the time systemd takes to set the scope up.
    With a tracer, the helper runs as the tracer's child inside the same scope.
    """
    script = script.resolve()
    inner = helper_command(script, args)
    launch = tracer.command(inner) if tracer is not None else inner
    invocation = invocation_id or new_invocation_id()
    unit = scope_unit_name(skill.skill_id, invocation)
    timed_out = False

    with (
        tempfile.TemporaryDirectory(prefix="cim-skill-", ignore_cleanup_errors=True) as home,
        tempfile.TemporaryFile() as out_f,
        tempfile.TemporaryFile() as err_f,
    ):
        env = [f"{key}={value}" for key, value in clean_env(home).items()]
        cmd = [
            "systemd-run", "--user", "--scope", "--quiet", f"--unit={unit}", "--",
            "env", "-i", *env, "/bin/sh", "-c", _GATE, "cim-gate", *launch,
        ]  # fmt: skip
        proc = subprocess.Popen(
            cmd,
            cwd=skill.path,
            stdin=subprocess.PIPE,
            stdout=out_f,
            stderr=err_f,
            bufsize=0,
        )
        cgroup: Path | None = None
        try:
            cgroup = _await_scope(proc, unit)
            if cgroup is None:
                proc.kill()
                proc.wait()
                detail = read_output(err_f).strip() or "systemd did not place it in a scope"
                raise ScopeError(f"{unit}.scope was not created: {detail}")

            # Our direct child is the helper, or the tracer when there is one.
            seen: dict[int, Member] = {}
            if tracer is None:
                seen[proc.pid] = Member(proc.pid, Path(inner[0]).name[:COMM_MAX])

            def helper_members() -> list[Member]:
                found = _read_members(cgroup)
                if tracer is not None:
                    return [member for member in found if member.pid != proc.pid]
                # Until the gate has exec'd the helper, its PID still carries a launcher's name.
                return [m for m in found if m.pid != proc.pid or m.comm not in _LAUNCH_COMMS]

            helper_status: int | None = None
            _open_gate(proc)
            deadline = time.monotonic() + timeout
            while True:
                for member in helper_members():
                    seen[member.pid] = member
                try:
                    proc.wait(timeout=POLL_INTERVAL_S)
                    break
                except subprocess.TimeoutExpired:
                    if tracer is not None:
                        helper_status = tracer.helper_exit()
                        if helper_status is not None:
                            break
                    if time.monotonic() >= deadline:
                        timed_out = True
                        _kill_scope(cgroup, unit)
                        proc.kill()
                        proc.wait()
                        _wait_empty(cgroup)
                        break

            leaked = tuple(helper_members())
            for member in leaked:
                seen[member.pid] = member
            if leaked:
                _kill_scope(cgroup, unit)
                _wait_empty(cgroup)
            if tracer is not None and not timed_out:
                try:  # with nothing left to trace, the tracer exits by itself
                    proc.wait(timeout=SETTLE_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    _kill_scope(cgroup, unit)
                    proc.kill()
                    proc.wait()
                if helper_status is None:
                    helper_status = tracer.helper_exit()
        finally:
            if proc.poll() is None:  # interrupted: never leave a helper running unobserved
                if cgroup is not None:
                    _kill_scope(cgroup, unit)
                proc.kill()
                proc.wait()

        stdout = read_output(out_f)
        stderr = read_output(err_f)

    returncode = proc.returncode if helper_status is None else helper_status
    if timed_out:
        returncode = TIMEOUT_RETURNCODE
    if timed_out:
        stderr = with_timeout_note(stderr, timeout)
    result = RunResult(skill.skill_id, script, returncode, stdout, stderr)
    members = tuple(sorted(seen.values(), key=lambda m: m.pid))
    return ScopedRunResult(result, invocation, unit, cgroup, Path(home), members, leaked)
