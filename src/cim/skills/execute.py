"""Run one skill helper for an agent harness, traced and recorded: `python -m cim.skills exec`.

The skills twin of `cim proxy` (T-13 design note, section 5). The agent harness calls it in
place of running the helper itself. The helper runs as `observe` runs it: in its own cgroup
scope under strace (cim.skills.collector). One behaviour record goes into the store under
the skill (with a behaviour alert if the run leaves the skill's learned pattern), and the
helper's output and exit status go back to the caller.

Rules:
- The skill must be installed under one of the roots, and the script must be a helper
  inside that skill's own directory. Anything else is refused before the helper runs.
- The helper never runs untraced. Without a systemd user session or strace, exec stops
  with EXIT_NOT_TRACED.
- Everything exec writes to the store goes through store_behaviour(). ADR-007 and T-13
  decision 8: that function is what the single store writer replaces later.
- The run is scored as it is recorded (T-16, in record_behaviour). A behaviour alert is
  stored and named on stderr; it does not change the exit status, which stays the helper's.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from cim.common.store import BaselineStore
from cim.skills.collector import (
    Observation,
    Recorded,
    TraceError,
    observe,
    record_behaviour,
    tracer_available,
)
from cim.skills.inventory import DEFAULT_ORIGIN, installed_skills
from cim.skills.runner import (
    HELPER_SUFFIXES,
    MAX_OUTPUT_BYTES,
    TIMEOUT_RETURNCODE,
    Captured,
    Skill,
)
from cim.skills.scoped import ScopeError, scope_available

DEFAULT_TIMEOUT_S = 30.0
# Codes exec sets itself; everything else is the helper's own exit status.
EXIT_USAGE = 2
EXIT_NOT_TRACED = 125  # no behaviour record for this run
EXIT_REFUSED = 126  # the script was refused; the helper did not run
EXIT_UNKNOWN_SKILL = 127  # no such skill under the roots; the helper did not run

HELP = f"""\
Runs one helper of an installed skill the way `observe` does: in its own cgroup scope,
under strace, with a clean environment (PATH=/usr/bin:/bin and a throwaway HOME), the
skill directory as its working directory and stdin from /dev/null. What it did is
recorded in the store under the skill; a skill the store has not seen is baselined first.
No score is computed.

Put the script and its arguments after `--`. The script is a path relative to the skill
directory. Arguments are passed on unchanged, and relative ones resolve against the
skill directory.

Output: the helper's stdout and stderr are captured and handed on once it has finished,
not while it runs; stdout first, then stderr. stdout is handed on byte for byte, and exec
writes nothing of its own there. Each stream is capped at {MAX_OUTPUT_BYTES} bytes:
anything past the cap is dropped, and exec says on stderr how many bytes were lost. A
helper with more to say should write it to a file. exec's own messages go to stderr,
after the helper's.

Exit status: the helper's own, or 128+N if signal N killed it. exec sets these itself:
  {EXIT_USAGE}    usage error (bad arguments, no skill roots)
  {TIMEOUT_RETURNCODE}  the helper ran past --timeout and was killed
  {EXIT_NOT_TRACED}  no behaviour record: no systemd user session or no strace (the helper did
       not run), or the trace or the store write failed (stderr says which)
  {EXIT_REFUSED}  script refused: absolute, contains "..", leaves the skill directory through
       a symlink, missing, or not a .py / .sh helper (the helper did not run)
  {EXIT_UNKNOWN_SKILL}  no such skill under the roots (the helper did not run)
A helper that exits with one of these codes itself looks the same; exec's message on
stderr tells them apart.
"""


class ExecRefused(Exception):
    """exec will not run the helper. `code` is the exit status to stop with."""

    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Request:
    db: Path
    roots: tuple[Path, ...]
    skill_id: str
    script: str
    args: tuple[str, ...] = ()
    timeout: float = DEFAULT_TIMEOUT_S
    origin: str = DEFAULT_ORIGIN
    verbose: bool = False


def find_skill(roots: Iterable[Path], skill_id: str) -> Skill:
    """The installed skill with this id, named as the inventory names it (`name#2`, ...)."""
    skills = installed_skills(roots)
    if skill_id not in skills:
        raise ExecRefused(f"no skill {skill_id!r} under the skill roots", EXIT_UNKNOWN_SKILL)
    return skills[skill_id]


def resolve_script(skill: Skill, script: str) -> Path:
    """The helper's real path, refused unless it is a helper inside the skill's directory."""
    relative = Path(script)
    if not script or relative.is_absolute():
        raise ExecRefused(f"script must be relative to the skill: {script!r}", EXIT_REFUSED)
    if ".." in relative.parts:
        raise ExecRefused(f"script must not contain '..': {script!r}", EXIT_REFUSED)
    base = skill.path.resolve()
    try:
        target = (base / relative).resolve(strict=True)
    except (OSError, RuntimeError):  # missing, or a symlink loop
        raise ExecRefused(f"no such script in {skill.skill_id}: {script}", EXIT_REFUSED) from None
    if not target.is_relative_to(base):
        raise ExecRefused(f"script leaves the skill directory: {script} -> {target}", EXIT_REFUSED)
    if not target.is_file() or target.suffix not in HELPER_SUFFIXES:
        kinds = " or ".join(sorted(HELPER_SUFFIXES))
        raise ExecRefused(f"not a helper script ({kinds}): {script}", EXIT_REFUSED)
    return target


def store_behaviour(db: Path, skill: Skill, observation: Observation, origin: str) -> Recorded:
    """Every store write exec makes goes through here (ADR-007, T-13 decision 8).

    For December it opens the store and writes the record itself, as `cim proxy` does. Once
    `cim watch` runs the single store writer, this becomes the client that hands the
    observation to it, and nothing else in exec changes.
    """
    with BaselineStore(db) as store:
        return record_behaviour(store, skill, observation, origin=origin)


def exit_status(returncode: int) -> int:
    """A process exit status for the caller: a helper killed by signal N gives 128+N."""
    return 128 - returncode if returncode < 0 else returncode


def _note(err: BinaryIO, message: str) -> None:
    err.write(f"exec: {message}\n".encode())
    err.flush()


def _dropped(err: BinaryIO, name: str, stream: Captured) -> None:
    if stream.dropped:
        _note(
            err,
            f"{name} cut at {MAX_OUTPUT_BYTES} bytes: {stream.dropped} of {stream.size} "
            "bytes were dropped",
        )


def run(request: Request, out: BinaryIO, err: BinaryIO) -> int:
    """Run the request's helper traced, record it, hand its output on. Returns the exit status."""
    try:
        if not request.roots:
            raise ExecRefused("give --root or set CIM_SKILL_ROOTS", EXIT_USAGE)
        skill = find_skill(request.roots, request.skill_id)
        script = resolve_script(skill, request.script)
        if not scope_available():
            raise ExecRefused(
                "needs a systemd user session (cgroup scope per invocation); "
                "the helper was not run",
                EXIT_NOT_TRACED,
            )
        if not tracer_available():
            raise ExecRefused(
                "needs strace, and permission to trace a child process; the helper was not run",
                EXIT_NOT_TRACED,
            )
        observation = observe(skill, script, request.args, timeout=request.timeout)
    except ExecRefused as refused:
        _note(err, str(refused))
        return refused.code
    except ScopeError as exc:
        _note(err, f"{exc}; the helper was not run")
        return EXIT_NOT_TRACED
    except TraceError as exc:
        _note(err, f"{exc}; the helper ran but nothing was recorded")
        return EXIT_NOT_TRACED

    # Record first: the evidence must not depend on the caller reading the output.
    stored: Exception | None = None
    recorded: Recorded | None = None
    try:
        recorded = store_behaviour(request.db, skill, observation, request.origin)
    except Exception as exc:  # any failure here must reach the caller, not hide behind output
        stored = exc

    result = observation.run.result
    out.write(result.raw_stdout.data)
    out.flush()
    err.write(result.raw_stderr.data)
    err.flush()
    _dropped(err, "stdout", result.raw_stdout)
    _dropped(err, "stderr", result.raw_stderr)
    if observation.run.leaked:
        _note(err, f"{len(observation.run.leaked)} process(es) outlived the helper and were killed")
    if stored is not None:
        _note(err, f"the helper ran but its behaviour was not recorded: {stored}")
        return EXIT_NOT_TRACED
    if recorded is not None and recorded.alert is not None:
        _note(err, f"behaviour alert: {recorded.alert.detail}")
    if recorded is not None and recorded.score_error is not None:
        _note(err, f"the run was recorded but could not be scored: {recorded.score_error}")
    if request.verbose:
        events = ", ".join(f"{kind} {what}" for kind, what in observation.events) or "nothing"
        _note(
            err,
            f"recorded {skill.skill_id} {observation.invocation_id} "
            f"exit={result.returncode} processes={observation.process_count}: {events}",
        )
    return exit_status(result.returncode)
