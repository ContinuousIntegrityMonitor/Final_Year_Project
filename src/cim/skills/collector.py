"""Host behaviour collector (T-11): what one helper invocation did, attributed to its skill.

The helper runs in its own cgroup scope (cim.skills.scoped) under `strace -f`, which follows
every process the helper starts, double-forked grandchildren included. The trace gives every
program executed, every file written and every connection attempted, however briefly: a
child that lives for a millisecond is recorded like one that lives for a minute, and two runs
of the same helper give the same record.

Sampling /proc cannot do that. On the seed corpus it saw one process where the trace sees
five, and it never sees a connection that is refused.

Known limits:
- A traced program can tell it is traced and behave differently. Setuid programs run without
  their extra privilege while traced.
- The trace file belongs to the same user as the helper, like the cgroup (see scoped.py). A
  helper that actively evades can tamper with it. ADR-007: accepted for Phase 1; in Phase 2 the
  trace is written by a root-owned tracer into a directory only the monitor's user can write.
- Only what the helper asks the kernel for by name is recorded. Data written through a
  descriptor it inherited, or received from another process, is not a file-write target.
- A destination is classed by address. Which name was looked up is not recorded, so the
  `domain` class of the contract is never produced here.
"""

from __future__ import annotations

import functools
import ipaddress
import os
import re
import signal
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from cim.common.schema.alerts import BehaviourAlertPayload
from cim.common.schema.skills import Egress, SkillBehaviourPayload
from cim.common.store import BaselineStore
from cim.skills.alert import record_score_failure, score_run
from cim.skills.digest import record_path
from cim.skills.inventory import (
    DEFAULT_ORIGIN,
    append_event,
    describe_skill,
    known_skills,
    utc_now,
    write_baselines,
)
from cim.skills.runner import Skill
from cim.skills.scoped import ScopedRunResult, run_script_scoped

# One (directory descriptor index, path index) pair per path the call changes.
_WRITE_CALLS: dict[str, tuple[tuple[int | None, int], ...]] = {
    "creat": ((None, 0),),
    "rename": ((None, 0), (None, 1)),
    "renameat": ((0, 1), (2, 3)),
    "renameat2": ((0, 1), (2, 3)),
    "unlink": ((None, 0),),
    "unlinkat": ((0, 1),),
    "rmdir": ((None, 0),),
    "mkdir": ((None, 0),),
    "mkdirat": ((0, 1),),
    "symlink": ((None, 1),),
    "symlinkat": ((1, 2),),
    "link": ((None, 1),),
    "linkat": ((2, 3),),
    "truncate": ((None, 0),),
    "chmod": ((None, 0),),
    "fchmodat": ((0, 1),),
    "fchmodat2": ((0, 1),),
}
# open-family calls: (directory descriptor index, path index, flags index)
_OPEN_CALLS: dict[str, tuple[int | None, int, int]] = {
    "open": (None, 0, 1),
    "openat": (0, 1, 2),
    "openat2": (0, 1, 2),
}
_WRITE_FLAGS = re.compile(r"\bO_(WRONLY|RDWR|CREAT|TRUNC|APPEND)\b")
_SPAWN_CALLS = frozenset({"clone", "clone3", "fork", "vfork"})
_OTHER_CALLS = ("execve", "execveat", "chdir", "fchdir", "connect", "sendto")
TRACED_CALLS = (*_OTHER_CALLS, *_OPEN_CALLS, *_WRITE_CALLS, *sorted(_SPAWN_CALLS))

_LINE = re.compile(r"^(\d+)\s+(\d+)\.(\d{6})\s+(.*)$")
_UNFINISHED = " <unfinished ...>"
_RESUMED = re.compile(r"^<\.\.\. \w+ resumed>")
_EXIT = re.compile(r"^\+\+\+ (?:exited with (\d+)|killed by (SIG\w+))")
_CALL = re.compile(r"^(\w+)\((.*)\)\s+=\s+(-?\d+|\?)")
_ESCAPE = re.compile(rb"\\(x[0-9a-fA-F]{2}|[0-7]{1,3}|.)", re.DOTALL)
_SIMPLE_ESCAPES = {b"n": b"\n", b"t": b"\t", b"r": b"\r", b"v": b"\v", b"f": b"\f"}
_TEXT = "\x00"  # stands for one quoted string in a line's skeleton
_FD_PATH = "\x01"  # stands for one <...> descriptor path
_INET = re.compile(r"sa_family=AF_INET, sin_port=htons\((\d+)\), sin_addr=inet_addr\(\x00\)")
_INET6 = re.compile(r"sa_family=AF_INET6, sin6_port=htons\((\d+)\).*?inet_pton\(AF_INET6, \x00")
_UNIX = re.compile(r"sa_family=AF_UNIX, sun_path=@?\x00")
_TMP_ROOTS = ("/tmp", "/var/tmp", "/dev/shm")
_ROOT_DEPTH = 3
HOME_ROOT = "~"
SKILL_ROOT = "<skill>"


class TraceError(RuntimeError):
    """The helper could not be traced, so nothing can be said about what it did."""


@dataclass(frozen=True)
class Observation:
    """Everything one invocation was seen to do."""

    skill_id: str
    invocation_id: str
    cgroup_id: str
    binaries_executed: tuple[str, ...]  # every program run, the helper's interpreter first
    spawned: tuple[str, ...]  # programs run by processes the helper started
    file_write_targets: tuple[str, ...]  # path roots, see write_root()
    egress: tuple[Egress, ...]
    process_count: int
    duration_us: int
    run: ScopedRunResult

    @property
    def events(self) -> tuple[tuple[str, str], ...]:
        """What the helper did beyond running: empty for a helper that only computes."""
        found = [("spawn", binary) for binary in self.spawned]
        found += [("write", root) for root in self.file_write_targets]
        found += [("egress", f"{item.dest_class}:{item.port}") for item in self.egress]
        return tuple(found)

    def payload(self) -> SkillBehaviourPayload:
        return SkillBehaviourPayload(
            skill_id=self.skill_id,
            invocation_id=self.invocation_id,
            cgroup_id=self.cgroup_id,
            binaries_executed=list(self.binaries_executed),
            file_write_targets=list(self.file_write_targets),
            egress=list(self.egress),
            process_count=self.process_count,
            duration_us=self.duration_us,
        )


@dataclass
class Trace:
    """What a strace log says, before it is turned into contract fields."""

    main_pid: int | None = None
    exit_status: int | None = None
    started_us: int | None = None
    ended_us: int | None = None
    executed: list[tuple[int, str]] = field(default_factory=list)  # (pid, absolute path)
    written: list[str] = field(default_factory=list)  # absolute paths
    destinations: list[tuple[str, str, int]] = field(default_factory=list)  # family, addr, port
    processes: set[int] = field(default_factory=set)
    threads: set[int] = field(default_factory=set)


def _unescape(text: str) -> str:
    """Undo strace's C-style escapes. The result is always valid UTF-8 text."""

    def replace(match: re.Match[bytes]) -> bytes:
        body = match.group(1)
        if body[:1] == b"x":
            return bytes([int(body[1:], 16)])
        if body[:1].isdigit():
            return bytes([int(body, 8) & 0xFF])
        return _SIMPLE_ESCAPES.get(body, body)

    return record_path(os.fsdecode(_ESCAPE.sub(replace, text.encode("utf-8", "surrogateescape"))))


def _skeleton(text: str) -> tuple[str, list[str], list[str]]:
    """Split a line into structure, quoted strings and <...> descriptor paths.

    Paths and addresses are chosen by the helper. Lifting them out first means nothing in
    them can be mistaken for the structure of the line.
    """
    out: list[str] = []
    strings: list[str] = []
    fd_paths: list[str] = []
    i, n = 0, len(text)
    while i < n:
        opener = text[i]
        if opener not in '"<':
            out.append(opener)
            i += 1
            continue
        closer = '"' if opener == '"' else ">"
        j = i + 1
        while j < n and text[j] != closer:
            j += 2 if text[j] == "\\" else 1
        body = _unescape(text[i + 1 : j])
        if opener == '"':
            strings.append(body)
            out.append(_TEXT)
        else:
            fd_paths.append(body)
            out.append(_FD_PATH)
        i = j + 1
    return "".join(out), strings, fd_paths


def _split_args(skeleton: str) -> list[str]:
    args: list[str] = []
    depth, start = 0, 0
    for index, char in enumerate(skeleton):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            args.append(skeleton[start:index].strip())
            start = index + 1
    tail = skeleton[start:].strip()
    return [*args, tail] if tail else args


class _Line:
    """One completed system call, with its strings and descriptor paths back in place."""

    def __init__(self, name: str, body: str, result: str) -> None:
        self.name = name
        self.ok = not result.startswith("-") and result != "?"
        self.result = result
        skeleton, self._strings, self._fd_paths = _skeleton(body)
        self.args = _split_args(skeleton)
        self.skeleton = skeleton

    def _nth(self, marker: str, upto: str) -> int:
        return upto.count(marker)

    def string(self, index: int) -> str | None:
        """The quoted string that is argument `index`, if that argument is one."""
        if index >= len(self.args) or not self.args[index].startswith(_TEXT):
            return None
        before = ",".join(self.args[:index])
        return self._strings[self._nth(_TEXT, before)]

    def fd_path(self, index: int) -> str | None:
        """The path strace printed for the descriptor that is argument `index`."""
        if index >= len(self.args) or _FD_PATH not in self.args[index]:
            return None
        before = ",".join(self.args[:index])
        return self._fd_paths[self._nth(_FD_PATH, before)]

    def text_in(self, match: re.Match[str]) -> str:
        """The quoted string a pattern's \\x00 placeholder stood for."""
        upto = self.skeleton[: match.end()]
        return self._strings[upto.count(_TEXT) - 1]


def parse_trace(lines: list[str], cwd: str) -> Trace:
    """Read strace output (-f -ttt -y, one file) into a Trace. Unknown lines are skipped."""
    trace = Trace()
    pending: dict[int, str] = {}
    directory: dict[int, str] = {}

    def resolve(pid: int, line: _Line, dirfd: int | None, index: int) -> str | None:
        path = line.string(index)
        if path is None:
            return None
        if not path.startswith("/"):
            base = line.fd_path(dirfd) if dirfd is not None else None
            path = os.path.join(base or directory.get(pid, cwd), path)
        return os.path.normpath(path)

    for raw in lines:
        match = _LINE.match(raw)
        if match is None:
            continue
        pid = int(match.group(1))
        stamp = int(match.group(2)) * 1_000_000 + int(match.group(3))
        rest = match.group(4)
        if trace.main_pid is None:
            trace.main_pid, trace.started_us = pid, stamp
        trace.processes.add(pid)
        finished = _EXIT.match(rest)
        if finished is not None:
            if pid == trace.main_pid:
                trace.ended_us = stamp
                if finished.group(1) is not None:
                    trace.exit_status = int(finished.group(1))
                else:
                    number = getattr(signal, finished.group(2), None)
                    trace.exit_status = -int(number) if number is not None else -1
            continue
        if rest.endswith(_UNFINISHED):
            pending[pid] = rest[: -len(_UNFINISHED)]
            continue
        if _RESUMED.match(rest):
            rest = pending.pop(pid, "") + _RESUMED.sub("", rest, count=1)
        call = _CALL.match(rest)
        if call is None:
            continue
        line = _Line(call.group(1), call.group(2), call.group(3))
        name = line.name
        if name in ("connect", "sendto"):
            _read_destination(line, trace)
        if not line.ok:
            continue
        if name in _SPAWN_CALLS:
            child = int(line.result)
            if child > 0:
                trace.processes.add(child)
                directory[child] = directory.get(pid, cwd)
                if "CLONE_THREAD" in line.skeleton:
                    trace.threads.add(child)
        elif name in ("execve", "execveat"):
            target = resolve(pid, line, 0 if name == "execveat" else None, name == "execveat")
            if target is not None:
                trace.executed.append((pid, target))
        elif name == "chdir":
            target = resolve(pid, line, None, 0)
            if target is not None:
                directory[pid] = target
        elif name == "fchdir":
            target = line.fd_path(0)
            if target is not None:
                directory[pid] = target
        elif name in _OPEN_CALLS:
            dirfd, index, flags = _OPEN_CALLS[name]
            if flags < len(line.args) and _WRITE_FLAGS.search(line.args[flags]):
                target = resolve(pid, line, dirfd, index)
                if target is not None:
                    trace.written.append(target)
        elif name in _WRITE_CALLS:
            for dirfd, index in _WRITE_CALLS[name]:
                target = resolve(pid, line, dirfd, index)
                if target is not None:
                    trace.written.append(target)
    return trace


def _read_destination(line: _Line, trace: Trace) -> None:
    """Record where a connect or sendto was aimed.

    A network address counts whatever came of the call: a refused connection still sent a
    packet towards it. A unix socket counts only if the call succeeded. A failed one reached
    nobody, and on some systems every program makes one at start-up, looking for a
    name-service cache that is not running.
    """
    for family, pattern in (("inet", _INET), ("inet6", _INET6)):
        match = pattern.search(line.skeleton)
        if match is not None:
            trace.destinations.append((family, line.text_in(match), int(match.group(1))))
            return
    match = _UNIX.search(line.skeleton)
    if match is not None and line.ok:
        trace.destinations.append(("unix", line.text_in(match), 0))


def write_root(path: str, home: str, skill_dir: str) -> str | None:
    """The stable root a written path is reported under, or None if it is not a file write.

    Run-specific parts are dropped so the same helper gives the same value on every run:
    the invocation's own HOME is `~`, the skill directory is `<skill>`, temporary
    directories collapse to themselves, and anything else is its directory, at most three
    levels deep.
    """
    if path == "/dev/null":
        return None
    for prefix, label in ((home, HOME_ROOT), (skill_dir, SKILL_ROOT)):
        if path == prefix:
            return label
        if path.startswith(prefix + "/"):
            parts = path[len(prefix) + 1 :].split("/")
            return label if len(parts) == 1 else f"{label}/{parts[0]}"
    for root in _TMP_ROOTS:
        if path == root or path.startswith(root + "/"):
            return root
    parts = [part for part in os.path.dirname(path).split("/") if part]
    return "/" + "/".join(parts[:_ROOT_DEPTH])


def classify(family: str, address: str, port: int) -> Egress | None:
    if family == "unix":
        return Egress(dest_class="unix_socket", port=0)
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None
    mapped = getattr(ip, "ipv4_mapped", None)
    ip = mapped or ip
    if ip.is_unspecified:
        return None
    return Egress(dest_class="public_ip" if ip.is_global else "private_ip", port=port)


class StraceTracer:
    """Runs the helper under strace and follows the log while the helper runs."""

    def __init__(self, log: Path) -> None:
        self.log = log
        self.lines: list[str] = []
        self._offset = 0
        self._partial = b""
        self._main: str | None = None
        self._status: int | None = None

    def command(self, inner: list[str]) -> list[str]:
        calls = ",".join(f"?{name}" for name in TRACED_CALLS)  # ? = skip names this CPU lacks
        return [
            "strace", "-f", "-ttt", "-y", "-s", "0", "--seccomp-bpf", "-e", "signal=none",
            "-e", f"trace={calls}", "-o", str(self.log), "--", *inner,
        ]  # fmt: skip

    def helper_exit(self) -> int | None:
        try:
            with self.log.open("rb") as handle:
                handle.seek(self._offset)
                data = handle.read()
        except OSError:
            return self._status
        self._offset += len(data)
        *complete, self._partial = (self._partial + data).split(b"\n")
        for raw in complete:
            text = raw.decode("utf-8", errors="replace")
            self.lines.append(text)
            match = _LINE.match(text)
            if match is None:
                continue
            if self._main is None:
                self._main = match.group(1)
            finished = _EXIT.match(match.group(4))
            if finished is not None and match.group(1) == self._main and self._status is None:
                self._status = parse_trace([text], "/").exit_status
        return self._status


@functools.cache
def tracer_available() -> bool:
    """True if strace is installed and allowed to trace a child process here."""
    try:
        probe = subprocess.run(
            ["strace", "-f", "--seccomp-bpf", "-o", os.devnull, "-e", "trace=?execve", "true"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def observe(
    skill: Skill,
    script: Path,
    args: tuple[str, ...] = (),
    timeout: float = 30.0,
    invocation_id: str | None = None,
) -> Observation:
    """Run one helper in its scope under the tracer and report what it did.

    Call scope_available() and tracer_available() first. Raises TraceError if the helper
    could not be traced.
    """
    with tempfile.TemporaryDirectory(prefix="cim-trace-") as workdir:
        tracer = StraceTracer(Path(workdir) / "trace.log")
        run = run_script_scoped(skill, script, args, timeout, invocation_id, tracer)
        tracer.helper_exit()  # read whatever arrived after the helper finished
        trace = parse_trace(tracer.lines, str(skill.path.resolve()))
    if trace.main_pid is None:
        raise TraceError(f"no trace for {script.name}: {run.result.stderr.strip() or 'empty log'}")
    home = str(run.home)
    skill_dir = str(skill.path.resolve())
    roots = {write_root(path, home, skill_dir) for path in trace.written}
    egress = {classify(*destination) for destination in trace.destinations}
    # Sorted, so two runs of the same helper give the same record whatever order its
    # children happened to be scheduled in. The helper's own interpreter stays first.
    first = trace.executed[0][1] if trace.executed else None
    others = {path for _pid, path in trace.executed} - {first}
    executed = ([first] if first is not None else []) + sorted(others)
    spawned = sorted({path for pid, path in trace.executed if pid != trace.main_pid})
    ended = trace.ended_us if trace.ended_us is not None else _last_stamp(tracer.lines)
    return Observation(
        skill_id=skill.skill_id,
        invocation_id=run.invocation_id,
        cgroup_id=run.cgroup.name,
        binaries_executed=tuple(executed),
        spawned=tuple(spawned),
        file_write_targets=tuple(sorted(root for root in roots if root is not None)),
        egress=tuple(
            sorted((e for e in egress if e is not None), key=lambda e: (e.dest_class, e.port))
        ),
        process_count=len(trace.processes - trace.threads),
        duration_us=max(0, (ended or 0) - (trace.started_us or 0)),
        run=run,
    )


def _last_stamp(lines: list[str]) -> int | None:
    for raw in reversed(lines):
        match = _LINE.match(raw)
        if match is not None:
            return int(match.group(2)) * 1_000_000 + int(match.group(3))
    return None


@dataclass(frozen=True)
class Recorded:
    """What `record_behaviour` stored for one run."""

    record_id: int  # the behaviour record
    alert: BehaviourAlertPayload | None  # the skill_behaviour_drift alert it raised, if any
    score_error: str | None = None  # scoring failed; a skill_score_failed record says so


def record_behaviour(
    store: BaselineStore,
    skill: Skill,
    observation: Observation,
    *,
    origin: str = DEFAULT_ORIGIN,
    ts: str | None = None,
) -> Recorded:
    """Append one behaviour record for the invocation, under the skill's own artefact, and
    score it (T-16): a run that leaves the skill's learned pattern gets a
    `skill_behaviour_drift` alert right after its record.

    A skill the store has not seen yet is baselined first, so the record has an artefact to
    belong to. Scoring never loses the run: if it fails, the behaviour record stays and a
    `skill_score_failed` record names it.
    """
    stamp = ts or utc_now()
    known = known_skills(store)
    if skill.skill_id not in known:
        write_baselines(store, {skill.skill_id: describe_skill(skill)}, origin=origin, ts=stamp)
        known = known_skills(store)
    artefact_id = known[skill.skill_id].artefact_id
    record_id = append_event(store, artefact_id, "behaviour", observation.payload(), stamp)
    try:
        alert = score_run(
            store, artefact_id=artefact_id, skill_id=skill.skill_id, record_id=record_id, ts=stamp
        )
    except Exception as exc:  # noqa: BLE001 — scoring must never lose the run
        try:
            record_score_failure(
                store,
                artefact_id=artefact_id,
                skill_id=skill.skill_id,
                record_id=record_id,
                error=exc,
                ts=stamp,
            )
        except Exception:  # noqa: BLE001 — the store itself is failing; the run is kept
            pass
        return Recorded(record_id, None, f"{type(exc).__name__}: {exc}")
    return Recorded(record_id, alert)
