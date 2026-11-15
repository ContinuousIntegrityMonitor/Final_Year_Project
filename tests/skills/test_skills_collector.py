"""Host behaviour collector (T-11). Parser tests need nothing; live tests need strace."""

# Trace lines are quoted exactly as strace prints them, so they run long.
# ruff: noqa: E501

from __future__ import annotations

import json
import signal
import time
from pathlib import Path

import pytest

from cim.common.schema.envelope import Artefact, Event
from cim.common.schema.skills import Egress
from cim.common.store import BaselineStore
from cim.skills.__main__ import main
from cim.skills.collector import (
    StraceTracer,
    TraceError,
    classify,
    observe,
    parse_trace,
    record_behaviour,
    write_root,
)
from cim.skills.corpus import default_root, load_manifest
from cim.skills.inventory import known_skills
from cim.skills.runner import Skill, discover_skills

CWD = "/skills/alpha"


def trace_of(*lines: str) -> list[str]:
    return [line for line in lines]


# ---------------------------------------------------------------- reading a trace


def test_executions_writes_and_exit_status() -> None:
    trace = parse_trace(
        trace_of(
            '100 1700000000.000100 execve("/usr/bin/bash", [...], 0x7ff /* 3 vars */) = 0',
            '100 1700000000.000200 openat(AT_FDCWD</skills/alpha>, "notes.txt", O_RDONLY) = 3</skills/alpha/notes.txt>',
            '100 1700000000.000300 openat(AT_FDCWD</skills/alpha>, "out.txt", O_WRONLY|O_CREAT|O_TRUNC, 0666) = 3</skills/alpha/out.txt>',
            '100 1700000000.000400 openat(AT_FDCWD</skills/alpha>, "/etc/shadow", O_WRONLY) = -1 EACCES (Permission denied)',
            "100 1700000000.000500 clone(child_stack=NULL, flags=CLONE_CHILD_CLEARTID|SIGCHLD, child_tidptr=0x7f) = 101",
            '101 1700000000.000600 execve("/usr/bin/nope", [...], 0x55 /* 3 vars */) = -1 ENOENT (No such file or directory)',
            '101 1700000000.000700 execve("/usr/bin/mkdir", [...], 0x55 /* 3 vars */) = 0',
            '101 1700000000.000800 mkdir("made", 0777) = 0',
            "101 1700000000.000900 +++ exited with 0 +++",
            "100 1700000000.250000 +++ exited with 3 +++",
        ),
        CWD,
    )
    assert trace.main_pid == 100
    assert trace.exit_status == 3
    assert trace.ended_us - trace.started_us == 249_900  # type: ignore[operator]
    assert trace.executed == [(100, "/usr/bin/bash"), (101, "/usr/bin/mkdir")]
    assert trace.written == [
        "/skills/alpha/out.txt",
        "/skills/alpha/made",
    ]  # read and failed open left out
    assert trace.processes == {100, 101}


def test_interrupted_calls_are_joined_and_threads_are_not_processes() -> None:
    trace = parse_trace(
        trace_of(
            '200 1700000000.000001 execve("/usr/bin/python3", [...], 0x7 /* 3 vars */) = 0',
            "200 1700000000.000002 clone3({flags=CLONE_VM|CLONE_FS|CLONE_THREAD|CLONE_SETTLS, child_tid=0x7f} <unfinished ...>",
            '201 1700000000.000003 openat(AT_FDCWD</skills/alpha>, "t.txt", O_WRONLY|O_CREAT, 0644 <unfinished ...>',
            "200 1700000000.000004 <... clone3 resumed> => {parent_tid=[201]}, 88) = 201",
            "201 1700000000.000005 <... openat resumed>) = 5</skills/alpha/t.txt>",
            "201 1700000000.000006 +++ exited with 0 +++",
            "200 1700000000.000007 +++ killed by SIGKILL +++",
        ),
        CWD,
    )
    assert trace.written == ["/skills/alpha/t.txt"]
    assert trace.processes - trace.threads == {200}
    assert trace.exit_status == -int(signal.SIGKILL)


def test_relative_paths_follow_each_process_working_directory() -> None:
    trace = parse_trace(
        trace_of(
            '300 1700000000.000001 execve("/usr/bin/bash", [...], 0x7 /* 3 vars */) = 0',
            '300 1700000000.000002 chdir("sub") = 0',
            "300 1700000000.000003 clone(child_stack=NULL, flags=SIGCHLD) = 301",
            '301 1700000000.000004 mkdir("inside", 0777) = 0',  # child starts in the parent's cwd
            '300 1700000000.000005 chdir("/elsewhere") = 0',
            '300 1700000000.000006 unlink("gone.txt") = 0',
            '301 1700000000.000007 rename("a", "b") = 0',
            "301 1700000000.000008 fchdir(7</var/data>) = 0",
            '301 1700000000.000009 symlink("/target", "ln") = 0',
            '301 1700000000.000010 unlinkat(9</opt/dir>, "x/../y", 0) = 0',
        ),
        CWD,
    )
    assert trace.written == [
        "/skills/alpha/sub/inside",
        "/elsewhere/gone.txt",
        "/skills/alpha/sub/a",
        "/skills/alpha/sub/b",
        "/var/data/ln",
        "/opt/dir/y",
    ]


def test_connection_attempts_are_recorded_whatever_the_outcome() -> None:
    trace = parse_trace(
        trace_of(
            '400 1700000000.000001 execve("/usr/bin/python3", [...], 0x7 /* 3 vars */) = 0',
            '400 1700000000.000002 connect(3<socket:[11]>, {sa_family=AF_INET, sin_port=htons(9), sin_addr=inet_addr("127.0.0.1")}, 16) = -1 ECONNREFUSED (Connection refused)',
            '400 1700000000.000003 connect(4<socket:[12]>, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("93.184.216.34")}, 16) = -1 EINPROGRESS (Operation now in progress)',
            '400 1700000000.000004 sendto(5<socket:[13]>, ""..., 1, 0, {sa_family=AF_INET6, sin6_port=htons(5353), sin6_flowinfo=htonl(0), inet_pton(AF_INET6, "::1", &sin6_addr), sin6_scope_id=0}, 28) = 1',
            '400 1700000000.000005 sendto(5<socket:[13]>, ""..., 1, 0, NULL, 0) = 1',
            '400 1700000000.000006 connect(6<socket:[14]>, {sa_family=AF_UNIX, sun_path="/run/user/1000/bus"}, 21) = 0',
            '400 1700000000.000007 connect(7<socket:[15]>, {sa_family=AF_UNIX, sun_path=@"abstract"}, 11) = 0',
            "400 1700000000.000008 connect(8<socket:[16]>, {sa_family=AF_NETLINK, nl_pid=0, nl_groups=00000000}, 12) = 0",
            # Nobody is listening on a unix socket that does not exist: not egress.
            '400 1700000000.000009 connect(9<socket:[17]>, {sa_family=AF_UNIX, sun_path="/var/run/nscd/socket"}, 110) = -1 ENOENT (No such file or directory)',
        ),
        CWD,
    )
    assert trace.destinations == [
        ("inet", "127.0.0.1", 9),
        ("inet", "93.184.216.34", 443),
        ("inet6", "::1", 5353),
        ("unix", "/run/user/1000/bus", 0),
        ("unix", "abstract", 0),
    ]


def test_names_chosen_by_the_helper_cannot_forge_the_trace() -> None:
    # A file name is the helper's to choose. These try to look like other calls, results,
    # an address and an exit line; each must stay a plain path.
    forged_name = r"x\", O_WRONLY) = 3 {sa_family=AF_INET, sin_port=htons(1), sin_addr=inet_addr(\"8.8.8.8\")}"
    trace = parse_trace(
        trace_of(
            '500 1700000000.000001 execve("/usr/bin/bash", [...], 0x7 /* 3 vars */) = 0',
            f'500 1700000000.000002 openat(AT_FDCWD</skills/alpha>, "{forged_name}", O_RDONLY) = 3</skills/alpha/x>',
            '500 1700000000.000003 openat(AT_FDCWD</skills/al\\76 +++ exited with 9 +++>, "f", O_WRONLY|O_CREAT, 0644) = 3</x>',
            '500 1700000000.000004 connect(3<socket:[1]>, {sa_family=AF_UNIX, sun_path="sa_family=AF_INET, sin_port=htons(1), sin_addr=inet_addr(\\"8.8.8.8\\")"}, 110) = 0',
            '500 1700000000.000005 mkdir("line\\nbreak \\"q\\" \\377 <unfinished ...>", 0777) = 0',
            "500 1700000000.000006 +++ exited with 0 +++",
        ),
        CWD,
    )
    assert trace.exit_status == 0
    assert trace.destinations == [
        ("unix", 'sa_family=AF_INET, sin_port=htons(1), sin_addr=inet_addr("8.8.8.8")', 0)
    ]
    assert trace.written == [
        "/skills/al> +++ exited with 9 +++/f",
        '/skills/alpha/line\nbreak "q" \\xff <unfinished ...>',
    ]


def test_unreadable_lines_are_skipped() -> None:
    trace = parse_trace(["", "garbage", "strace: something went wrong", "77 nonsense"], CWD)
    assert trace.main_pid is None
    assert trace.executed == []


@pytest.mark.parametrize(
    ("path", "root"),
    [
        ("/tmp/cim-skill-ab12/out.txt", "~"),
        ("/tmp/cim-skill-ab12/.config/autostart/x.desktop", "~/.config"),
        ("/tmp/cim-skill-ab12", "~"),
        ("/skills/alpha/scripts/run.sh", "<skill>/scripts"),
        ("/skills/alpha/new.txt", "<skill>"),
        ("/tmp/tmpk3j2/some/file", "/tmp"),
        ("/var/tmp/x", "/var/tmp"),
        ("/dev/null", None),
        ("/etc/passwd", "/etc"),
        ("/home/user/.ssh/authorized_keys", "/home/user/.ssh"),
        ("/sys/fs/cgroup/user.slice/escape/cgroup.procs", "/sys/fs/cgroup"),
        ("/rootfile", "/"),
    ],
)
def test_write_root(path: str, root: str | None) -> None:
    assert write_root(path, "/tmp/cim-skill-ab12", "/skills/alpha") == root


@pytest.mark.parametrize(
    ("destination", "expected"),
    [
        (("inet", "127.0.0.1", 9), Egress(dest_class="private_ip", port=9)),
        (("inet", "10.10.10.30", 9000), Egress(dest_class="private_ip", port=9000)),
        (("inet", "93.184.216.34", 443), Egress(dest_class="public_ip", port=443)),
        (("inet6", "::1", 53), Egress(dest_class="private_ip", port=53)),
        (("inet6", "::ffff:93.184.216.34", 443), Egress(dest_class="public_ip", port=443)),
        (("unix", "/run/user/1000/bus", 0), Egress(dest_class="unix_socket", port=0)),
        (("inet", "0.0.0.0", 0), None),
        (("inet", "not-an-address", 1), None),
    ],
)
def test_classify(destination: tuple[str, str, int], expected: Egress | None) -> None:
    assert classify(*destination) == expected


# ---------------------------------------------------------------- live runs


def make_skill(root: Path, name: str, body: str, suffix: str = "sh") -> tuple[Skill, Path]:
    skill_dir = root / name
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    (skill_dir / "scripts" / f"run.{suffix}").write_text(body, encoding="utf-8")
    skill = next(s for s in discover_skills(root) if s.skill_id == name)
    return skill, skill.helper_scripts[0]


ACTIVE = """\
echo data > "$HOME/out.txt"
exec 3<>/dev/tcp/127.0.0.1/9
# A double-forked grandchild: its own write, its own socket, its own program.
( ( mkdir "$HOME/deep"; echo deep > "$HOME/deep/file"; exec 3<>/dev/tcp/127.0.0.1/7; sleep 30 ) & )
sleep 0.5
"""


@pytest.mark.usefixtures("needs_tracer")
def test_spawn_write_and_socket_are_all_attributed_including_a_grandchild(tmp_path: Path) -> None:
    skill, script = make_skill(tmp_path, "active", ACTIVE)
    make_skill(tmp_path, "bystander", ":\n")
    seen = observe(skill, script)
    assert seen.skill_id == "active"
    assert seen.cgroup_id == f"cim-skill-active-{seen.invocation_id}.scope"
    kinds = {kind for kind, _ in seen.events}
    assert kinds == {"spawn", "write", "egress"}
    assert {"/usr/bin/mkdir", "/usr/bin/sleep"} <= set(seen.spawned)
    assert seen.file_write_targets == ("~", "~/deep")  # ~/deep was written by the grandchild
    assert seen.egress == (
        Egress(dest_class="private_ip", port=7),  # opened by the grandchild
        Egress(dest_class="private_ip", port=9),
    )
    assert seen.process_count >= 4
    assert [m.comm for m in seen.run.leaked] == ["sleep"]  # the grandchild was still there
    assert seen.run.result.returncode == 0


@pytest.mark.usefixtures("needs_tracer")
@pytest.mark.parametrize(("suffix", "body"), [("sh", ":\n"), ("py", "total = 1 + 1\n")])
def test_idle_benign_skill_yields_zero_events(tmp_path: Path, suffix: str, body: str) -> None:
    skill, script = make_skill(tmp_path, "idle", body, suffix)
    seen = observe(skill, script)
    assert seen.events == ()
    assert seen.process_count == 1
    assert len(seen.binaries_executed) == 1  # only its own interpreter
    assert seen.run.result.returncode == 0
    assert seen.run.result.stderr == ""  # the tracer adds nothing to the helper's output


@pytest.mark.usefixtures("needs_tracer")
def test_python_import_of_a_sibling_module_is_not_a_file_write(tmp_path: Path) -> None:
    skill, script = make_skill(tmp_path, "imports", "import sibling\n", "py")
    (skill.path / "scripts" / "sibling.py").write_text("VALUE = 7\n", encoding="utf-8")
    seen = observe(skill, script)
    assert seen.run.result.returncode == 0, seen.run.result.stderr
    assert seen.events == ()


@pytest.mark.usefixtures("needs_tracer")
def test_a_millisecond_child_and_a_refused_connection_are_not_missed(tmp_path: Path) -> None:
    body = "/usr/bin/true\nexec 3<>/dev/tcp/127.0.0.1/9\n"
    skill, script = make_skill(tmp_path, "quick", body)
    for _ in range(3):
        seen = observe(skill, script)
        assert seen.spawned == ("/usr/bin/true",)
        assert seen.egress == (Egress(dest_class="private_ip", port=9),)


@pytest.mark.usefixtures("needs_tracer")
def test_two_runs_give_the_same_record(tmp_path: Path) -> None:
    body = 'for n in 1 2 3; do ( echo $n > "$HOME/$n.txt" & ); done\nsort /dev/null | wc -l\nsleep 0.2\n'
    skill, script = make_skill(tmp_path, "steady", body)

    def stable(payload: dict[str, object]) -> dict[str, object]:
        varies = ("invocation_id", "cgroup_id", "duration_us")
        return {key: value for key, value in payload.items() if key not in varies}

    first = observe(skill, script).payload().model_dump(mode="json")
    second = observe(skill, script).payload().model_dump(mode="json")
    assert stable(first) == stable(second)
    assert first["binaries_executed"] == [
        "/usr/bin/bash",
        "/usr/bin/sleep",
        "/usr/bin/sort",
        "/usr/bin/wc",
    ]
    assert first["file_write_targets"] == ["~"]


@pytest.mark.usefixtures("needs_tracer")
def test_exit_status_and_signals_come_through_the_tracer(tmp_path: Path) -> None:
    skill, script = make_skill(tmp_path, "three", "exit 3\n")
    assert observe(skill, script).run.result.returncode == 3
    skill, script = make_skill(tmp_path, "term", "kill -TERM $$\nsleep 5\n")
    assert observe(skill, script).run.result.returncode == -int(signal.SIGTERM)


@pytest.mark.usefixtures("needs_tracer")
def test_timeout_still_reports_what_happened_before_it(tmp_path: Path) -> None:
    skill, script = make_skill(tmp_path, "slow", 'echo x > "$HOME/before.txt"\nsleep 60\n')
    started = time.monotonic()
    seen = observe(skill, script, timeout=1.0)
    assert time.monotonic() - started < 10
    assert seen.run.result.returncode == 124
    assert seen.spawned == ("/usr/bin/sleep",)
    assert seen.file_write_targets == ("~",)
    assert seen.run.leaked == ()


@pytest.mark.usefixtures("needs_tracer")
def test_killing_the_tracer_does_not_buy_time_unobserved(tmp_path: Path) -> None:
    # The tracer is the helper's parent and runs as the same user, so the helper can kill
    # it. Either the helper dies with its tracer or the runner finds it and kills the scope;
    # which one depends on the strace version. In both cases the run ends at once, the kill
    # shows in the exit status, and nothing is left running.
    skill, script = make_skill(tmp_path, "blind", "kill -KILL $PPID\nsleep 60\n")
    started = time.monotonic()
    seen = observe(skill, script)
    assert time.monotonic() - started < 10
    assert seen.run.result.returncode == -int(signal.SIGKILL)
    deadline = time.monotonic() + 3
    while seen.run.cgroup.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not seen.run.cgroup.exists()


@pytest.mark.usefixtures("needs_tracer")
def test_odd_names_and_relative_paths(tmp_path: Path) -> None:
    body = (
        'cd "$HOME"\n'
        "mkdir 'a\"b>c' \"$(printf 'bad\\377dir')\" plain\n"
        "echo x > 'a\"b>c/f'\n"
        "echo x > \"$(printf 'bad\\377dir')/f\"\n"
        "cd plain && echo x > rel.txt\n"
        'echo x > "$OLDPWD/top.txt"\n'
    )
    skill, script = make_skill(tmp_path, "odd", body)
    seen = observe(skill, script)
    assert seen.run.result.returncode == 0, seen.run.result.stderr
    assert seen.file_write_targets == ("~", '~/a"b>c', "~/bad\\xffdir", "~/plain")
    json.dumps(seen.payload().model_dump(mode="json")).encode("utf-8")


@pytest.mark.usefixtures("needs_tracer")
def test_write_inside_the_skill_directory_is_reported(tmp_path: Path) -> None:
    skill, script = make_skill(tmp_path, "selfmod", "echo '# changed' >> scripts/run.sh\n")
    assert observe(skill, script).file_write_targets == ("<skill>/scripts",)


@pytest.mark.usefixtures("needs_tracer")
def test_behaviour_record_is_stored_under_the_skill(tmp_path: Path) -> None:
    skill, script = make_skill(tmp_path / "skills", "active", ACTIVE)
    seen = observe(skill, script)
    with BaselineStore(tmp_path / "store.sqlite") as store:
        record_behaviour(store, skill, seen, ts="2026-11-15T12:00:00Z")
        record_behaviour(store, skill, observe(skill, script), ts="2026-11-15T12:00:05Z")
        records = store.read_records()
        artefact_id = known_skills(store)["active"].artefact_id
        assert store.verify_chain().ok
    assert [r.kind for r in records] == ["artefact", "behaviour", "behaviour"]  # one baseline
    assert {r.artefact_id for r in records} == {artefact_id}
    payload = json.loads(records[1].payload)
    Event(
        ts="2026-11-15T12:00:00Z",
        artefact=Artefact(type="skill", skill="active"),
        kind="behaviour",
        payload=payload,
    )
    assert payload == seen.payload().model_dump(mode="json")


@pytest.mark.usefixtures("needs_tracer")
def test_corpus_benign_skills_are_quiet_and_suspicious_ones_are_not() -> None:
    corpus = default_root()
    manifest = load_manifest(corpus)
    skills = {skill.skill_id: skill for skill in discover_skills(corpus)}
    seen = {
        skill_id: observe(
            skills[skill_id], skills[skill_id].path / entry.runs[0].script, entry.runs[0].args
        )
        for skill_id, entry in manifest.items()
    }
    for skill_id, entry in manifest.items():
        outcome = seen[skill_id]
        assert outcome.run.result.returncode == 0, (skill_id, outcome.run.result.stderr)
        if entry.label == "benign":
            assert not [e for e in outcome.egress if e.dest_class != "unix_socket"], skill_id
            assert outcome.run.leaked == (), skill_id
    for quiet in (
        "word-count",
        "json-format",
        "csv-summary",
        "date-convert",
        "markdown-toc",
        "unit-convert",
    ):
        assert seen[quiet].events == (), quiet
    assert seen["notes-sync"].egress == (Egress(dest_class="private_ip", port=9),)
    assert [m.comm for m in seen["cache-warmer"].run.leaked] == ["sleep"]
    assert "~/.config" in seen["cache-warmer"].file_write_targets
    assert {"/usr/bin/base64", "/usr/bin/sh"} <= set(seen["dep-installer"].spawned)
    assert "~/.local" in seen["dep-installer"].file_write_targets


@pytest.mark.usefixtures("needs_tracer")
def test_a_tracer_that_cannot_start_is_an_error_not_an_empty_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill, script = make_skill(tmp_path, "idle", ":\n")
    monkeypatch.setattr(
        StraceTracer, "command", lambda self, inner: ["strace", "--no-such-option", "--", *inner]
    )
    with pytest.raises(TraceError, match="no trace for run.sh"):
        observe(skill, script)


@pytest.mark.usefixtures("needs_tracer")
def test_command_line_observe(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "store.sqlite"
    code = main(["observe", "--db", str(db), "--skill", "notes-sync", "--skill", "word-count"])
    out = capsys.readouterr().out
    assert code == 0
    assert (
        "observe: notes-sync scripts/sync.py exit=0 processes=1 leaked=0: egress private_ip:9"
        in out
    )
    assert "observe: word-count scripts/count.py exit=0 processes=1 leaked=0: nothing" in out
    with BaselineStore(db) as store:
        assert [r.kind for r in store.read_records()].count("behaviour") == 2
        assert store.verify_chain().ok
