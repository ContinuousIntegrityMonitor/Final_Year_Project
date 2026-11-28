"""`python -m cim.skills exec`: one traced, recorded helper run for an agent harness (T-11).

Refusals are checked before anything runs, so those tests need no tracer. Live runs use the
needs_tracer fixture.
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path

import pytest

from cim.common.schema.skills import SkillBehaviourPayload
from cim.common.store import BaselineStore
from cim.skills import execute
from cim.skills.__main__ import main
from cim.skills.board import load_skills_board
from cim.skills.execute import (
    EXIT_NOT_TRACED,
    EXIT_REFUSED,
    EXIT_UNKNOWN_SKILL,
    EXIT_USAGE,
    exit_status,
    find_skill,
)
from cim.skills.inventory import ROOTS_ENV
from cim.skills.runner import MAX_OUTPUT_BYTES, TIMEOUT_RETURNCODE

MARKER = "ran.marker"  # a helper that runs leaves this in its skill directory


def make_skill(root: Path, name: str, body: str, suffix: str = "sh") -> Path:
    skill_dir = root / name
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    (skill_dir / "scripts" / f"run.{suffix}").write_text(body, encoding="utf-8")
    return skill_dir


def run_exec(capsysbinary: pytest.CaptureFixture[bytes], *argv: str) -> tuple[int, bytes, str]:
    code = main(["exec", *argv])
    captured = capsysbinary.readouterr()
    return code, captured.out, captured.err.decode("utf-8", errors="replace")


def behaviour_payloads(db: Path) -> list[dict[str, object]]:
    with BaselineStore(db) as store:
        records = store.read_records()
    return [json.loads(r.payload) for r in records if r.kind == "behaviour"]


# ---------------------------------------------------------------- refused before running


@pytest.fixture
def skills(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    skill = make_skill(root, "alpha", f"touch {MARKER}\necho hi\n")
    (skill / "notes.txt").write_text("not a helper\n", encoding="utf-8")
    (tmp_path / "outside.sh").write_text(f"touch {MARKER}\n", encoding="utf-8")
    (skill / "scripts" / "escape.sh").symlink_to(tmp_path / "outside.sh")
    (skill / "scripts" / "inside.sh").symlink_to(skill / "scripts" / "run.sh")
    make_skill(root, "beta", "echo beta\n")
    return root


@pytest.mark.parametrize(
    ("script", "says"),
    [
        ("/bin/true", "relative to the skill"),
        ("scripts/../scripts/run.sh", "'..'"),
        ("../beta/scripts/run.sh", "'..'"),
        ("scripts/escape.sh", "leaves the skill directory"),
        ("scripts/missing.sh", "no such script"),
        ("notes.txt", "not a helper script"),
        ("scripts", "not a helper script"),
        ("", "relative to the skill"),
    ],
)
def test_a_script_outside_the_skill_or_not_a_helper_is_refused(
    skills: Path, tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes], script: str, says: str
) -> None:
    db = tmp_path / "store.sqlite"
    code, out, err = run_exec(
        capsysbinary, "--db", str(db), "--root", str(skills), "alpha", "--", script
    )
    assert code == EXIT_REFUSED
    assert out == b""
    assert says in err and err.startswith("exec: ")
    assert not db.exists()  # refusing writes nothing
    assert not (skills / "alpha" / MARKER).exists() and not (tmp_path / MARKER).exists()


def test_an_unknown_skill_is_refused(
    skills: Path, tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    db = tmp_path / "store.sqlite"
    code, out, err = run_exec(
        capsysbinary, "--db", str(db), "--root", str(skills), "gamma", "--", "scripts/run.sh"
    )
    assert code == EXIT_UNKNOWN_SKILL
    assert out == b"" and "no skill 'gamma'" in err
    assert not db.exists()


def test_without_roots_it_is_a_usage_error(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ROOTS_ENV, raising=False)
    code, _out, err = run_exec(
        capsysbinary, "--db", str(tmp_path / "s.sqlite"), "alpha", "--", "scripts/run.sh"
    )
    assert code == EXIT_USAGE and "CIM_SKILL_ROOTS" in err


def test_roots_come_from_the_environment_when_no_root_is_given(
    skills: Path,
    tmp_path: Path,
    capsysbinary: pytest.CaptureFixture[bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ROOTS_ENV, os.pathsep.join([str(tmp_path / "absent"), str(skills)]))
    db = str(tmp_path / "s.sqlite")
    # Found (so the script check is reached) rather than unknown.
    assert run_exec(capsysbinary, "--db", db, "alpha", "--", "../x.sh")[0] == EXIT_REFUSED
    assert run_exec(capsysbinary, "--db", db, "gamma", "--", "x.sh")[0] == EXIT_UNKNOWN_SKILL


def test_a_second_copy_is_named_as_the_inventory_names_it(tmp_path: Path) -> None:
    make_skill(tmp_path / "one", "alpha", "echo one\n")
    second = make_skill(tmp_path / "two", "alpha", "echo two\n")
    found = find_skill([tmp_path / "one", tmp_path / "two"], "alpha#2")
    assert found.skill_id == "alpha#2" and found.path == second


@pytest.mark.parametrize(
    ("missing", "says"), [("scope", "systemd user session"), ("tracer", "strace")]
)
def test_without_scope_or_tracer_it_stops_and_never_runs_untraced(
    skills: Path,
    tmp_path: Path,
    capsysbinary: pytest.CaptureFixture[bytes],
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
    says: str,
) -> None:
    monkeypatch.setattr(execute, "scope_available", lambda: missing != "scope")
    monkeypatch.setattr(execute, "tracer_available", lambda: missing != "tracer")
    db = tmp_path / "store.sqlite"
    code, out, err = run_exec(
        capsysbinary, "--db", str(db), "--root", str(skills), "alpha", "--", "scripts/run.sh"
    )
    assert code == EXIT_NOT_TRACED
    assert out == b""
    assert says in err and "the helper was not run" in err
    assert not (skills / "alpha" / MARKER).exists()
    assert not db.exists()


def test_exit_status_of_a_signalled_helper_is_128_plus_the_signal() -> None:
    assert exit_status(0) == 0
    assert exit_status(3) == 3
    assert exit_status(-int(signal.SIGTERM)) == 128 + int(signal.SIGTERM)


# ---------------------------------------------------------------- live runs

# Writes bytes that are not UTF-8 and no trailing newline, a line to stderr, a file in HOME,
# runs a child program, and exits 3.
LOUD = """\
import subprocess, sys
sys.stdout.buffer.write(b"caf\\xc3\\xa9 \\xff\\xfe raw\\r\\nend")
sys.stderr.write("warning: from the helper\\n")
open(sys.argv[1] if len(sys.argv) > 1 else "/dev/null", "w").close()
subprocess.run(["/usr/bin/true"], check=True)
print(repr(sys.argv[1:]), file=sys.stderr)
sys.exit(3)
"""


@pytest.mark.usefixtures("needs_tracer")
def test_output_and_exit_code_pass_through_and_the_run_is_recorded(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    root = tmp_path / "skills"
    make_skill(root, "loud", LOUD, "py")
    db = tmp_path / "store.sqlite"
    base = ["--db", str(db), "--root", str(root), "loud", "--", "scripts/run.py"]

    code, out, err = run_exec(capsysbinary, *base, "out.txt", "--", "--flag")
    assert code == 3
    assert out == b"caf\xc3\xa9 \xff\xfe raw\r\nend"  # byte for byte, nothing added
    assert err == "warning: from the helper\n['out.txt', '--', '--flag']\n"  # exec added nothing

    with BaselineStore(db) as store:
        records = store.read_records()
        assert store.verify_chain().ok
    assert [r.kind for r in records] == ["artefact", "behaviour"]  # baselined first
    (payload,) = behaviour_payloads(db)
    SkillBehaviourPayload.model_validate(payload)  # a contract record
    assert payload["skill_id"] == "loud"
    assert payload["binaries_executed"][1:] == ["/usr/bin/true"]  # type: ignore[index]
    assert payload["file_write_targets"] == ["<skill>"]  # out.txt, in the skill directory
    assert records[1].artefact_id == records[0].artefact_id

    # A second run is recorded under the same baseline.
    assert run_exec(capsysbinary, *base)[0] == 3
    with BaselineStore(db) as store:
        kinds = [r.kind for r in store.read_records()]
    assert kinds == ["artefact", "behaviour", "behaviour"]
    row = next(r for r in load_skills_board(db).skills if r.skill_id == "loud")
    assert row.runs == 2


@pytest.mark.usefixtures("needs_tracer")
def test_a_signal_and_a_timeout_give_their_own_exit_codes(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    root = tmp_path / "skills"
    make_skill(root, "term", "kill -TERM $$\nsleep 5\n")
    make_skill(root, "slow", "echo started\nsleep 30\n")
    db = str(tmp_path / "store.sqlite")
    code, _out, _err = run_exec(
        capsysbinary, "--db", db, "--root", str(root), "term", "--", "scripts/run.sh"
    )
    assert code == 128 + int(signal.SIGTERM)
    code, out, err = run_exec(
        capsysbinary,
        "--db",
        db,
        "--root",
        str(root),
        "--timeout",
        "1",
        "slow",
        "--",
        "scripts/run.sh",
    )
    assert code == TIMEOUT_RETURNCODE
    assert out == b"started\n"
    assert err.endswith("timeout after 1.0s")
    assert len(behaviour_payloads(Path(db))) == 2  # both runs are recorded


@pytest.mark.usefixtures("needs_tracer")
def test_output_past_the_cap_is_dropped_and_the_caller_is_told(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    root = tmp_path / "skills"
    extra = 100
    make_skill(
        root, "big", f"import sys\nsys.stdout.write('x' * {MAX_OUTPUT_BYTES + extra})\n", "py"
    )
    code, out, err = run_exec(
        capsysbinary,
        "--db",
        str(tmp_path / "s.sqlite"),
        "--root",
        str(root),
        "big",
        "--",
        "scripts/run.py",
    )
    assert code == 0
    assert out == b"x" * MAX_OUTPUT_BYTES
    assert f"stdout cut at {MAX_OUTPUT_BYTES} bytes: {extra} of {MAX_OUTPUT_BYTES + extra}" in err


@pytest.mark.usefixtures("needs_tracer")
def test_a_failed_store_write_still_hands_the_output_on_but_says_so(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "skills"
    make_skill(root, "alpha", "echo hello\n")

    def broken(*_args: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(execute, "store_behaviour", broken)
    code, out, err = run_exec(
        capsysbinary,
        "--db",
        str(tmp_path / "s.sqlite"),
        "--root",
        str(root),
        "alpha",
        "--",
        "scripts/run.sh",
    )
    assert code == EXIT_NOT_TRACED
    assert out == b"hello\n"
    assert "not recorded: disk full" in err


# ---------------------------------------------------------------- through `cim skills exec`


def test_cim_skills_hands_on_the_arguments_exactly_as_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Click drops the first `--`; the `cim skills` mount must not (found rehearsing T-18)."""
    from typer.testing import CliRunner

    import cim.skills.__main__ as skills_main
    from cim.cli import app

    seen: list[list[str]] = []
    monkeypatch.setattr(skills_main, "main", lambda argv: seen.append(argv) or 0)
    typed = ["exec", "--db", "s", "word-count", "--", "scripts/x.py", "a", "--host", "h", "--"]
    result = CliRunner().invoke(app, ["skills", *typed])
    assert result.exit_code == 0, result.output
    assert seen == [typed]


@pytest.mark.usefixtures("needs_tracer")
def test_cim_skills_exec_passes_helper_flags_after_the_separator(tmp_path: Path) -> None:
    import subprocess
    import sys

    root = tmp_path / "skills"
    make_skill(root, "echo", 'printf "%s\\n" "$@"\n')
    db = tmp_path / "store.sqlite"
    done = subprocess.run(
        [sys.executable, "-m", "cim", "skills", "exec", "--db", str(db), "--root", str(root)]
        + ["echo", "--", "scripts/run.sh", "notes.md", "--host", "127.0.0.1", "--port", "9"],
        capture_output=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout == b"notes.md\n--host\n127.0.0.1\n--port\n9\n"
    assert len(behaviour_payloads(db)) == 1
