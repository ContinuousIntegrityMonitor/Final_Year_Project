"""Per-invocation cgroup scope tests (T-05). Live tests need a systemd user session."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from cim.skills.runner import Skill, discover_skills
from cim.skills.scoped import (
    CGROUP_ROOT,
    ScopeError,
    cgroup_path_from_proc,
    new_invocation_id,
    run_script_scoped,
    scope_available,
    scope_unit_name,
)


@pytest.fixture(scope="module")
def needs_scope() -> None:
    if not scope_available():
        pytest.skip("no systemd user session (cannot create transient scopes)")


def make_skill(root: Path, name: str, script_body: str) -> tuple[Skill, Path]:
    skill_dir = root / name
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test skill\n---\n", encoding="utf-8"
    )
    (skill_dir / "scripts" / "run.sh").write_text(script_body, encoding="utf-8")
    skill = discover_skills(root)[0]
    return skill, skill.helper_scripts[0]


def wait_until_gone(path: Path | None, seconds: float = 3.0) -> bool:
    if path is None:
        return False
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not path.exists():
            return True
        time.sleep(0.05)
    return not path.exists()


def test_unit_name_is_systemd_safe() -> None:
    assert scope_unit_name("my skill/v2", "inv-abc") == "cim-skill-my_skill_v2-inv-abc"


def test_unit_name_sanitises_the_invocation_id_and_bounds_the_skill_id() -> None:
    assert scope_unit_name("s", "inv/1 2") == "cim-skill-s-inv_1_2"
    assert len(scope_unit_name("x" * 500, "inv-abc") + ".scope") <= 255


def test_invocation_ids_are_unique() -> None:
    assert new_invocation_id() != new_invocation_id()


def test_cgroup_path_from_proc() -> None:
    text = "0::/user.slice/user-1000.slice/user@1000.service/app.slice/x.scope\n"
    expected = CGROUP_ROOT / "user.slice/user-1000.slice/user@1000.service/app.slice/x.scope"
    assert cgroup_path_from_proc(text) == expected


def test_cgroup_path_absent_without_v2_entry() -> None:
    assert cgroup_path_from_proc("12:cpu:/foo\n") is None


def test_unsupported_suffix_rejected(tmp_path: Path) -> None:
    skill = Skill("s", tmp_path, "s", "", ())
    with pytest.raises(ValueError):
        run_script_scoped(skill, tmp_path / "x.rb")


@pytest.mark.usefixtures("needs_scope")
def test_membership_includes_grandchild_and_leak_is_cleaned(tmp_path: Path) -> None:
    skill, script = make_skill(tmp_path, "spawner", "sleep 1 &\n( sleep 30 & )\nwait\n")
    out = run_script_scoped(skill, script)
    assert out.result.returncode == 0
    assert out.unit.startswith("cim-skill-spawner-inv-")
    assert len([m for m in out.members if m.comm == "sleep"]) >= 2
    assert any(m.comm == "sleep" for m in out.leaked)
    assert wait_until_gone(out.cgroup)


@pytest.mark.usefixtures("needs_scope")
def test_timeout_kills_whole_scope(tmp_path: Path) -> None:
    skill, script = make_skill(tmp_path, "sleeper", "sleep 30\n")
    start = time.monotonic()
    out = run_script_scoped(skill, script, timeout=1.0)
    assert out.result.returncode == 124
    assert time.monotonic() - start < 10
    assert wait_until_gone(out.cgroup)


@pytest.mark.usefixtures("needs_scope")
def test_environment_is_clean_inside_scope(tmp_path: Path) -> None:
    skill, script = make_skill(tmp_path, "envdump", "env\n")
    out = run_script_scoped(skill, script)
    assert out.result.returncode == 0
    assert "HOME=" in out.result.stdout
    assert "XDG_RUNTIME_DIR" not in out.result.stdout
    assert "DBUS_SESSION_BUS_ADDRESS" not in out.result.stdout


def wait_until_dead(pid: int, seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not Path(f"/proc/{pid}").exists():
            return True
        time.sleep(0.05)
    return not Path(f"/proc/{pid}").exists()


@pytest.mark.usefixtures("needs_scope")
def test_instant_helper_is_still_recorded(tmp_path: Path) -> None:
    skill, script = make_skill(tmp_path, "instant", "true\n")
    out = run_script_scoped(skill, script, invocation_id="inv-fixed")
    assert out.result.returncode == 0
    assert out.invocation_id == "inv-fixed"
    assert out.cgroup.name == "cim-skill-instant-inv-fixed.scope"
    assert [m.comm for m in out.members] == ["bash"]
    assert out.leaked == ()


@pytest.mark.usefixtures("needs_scope")
def test_instant_helper_cannot_leave_a_daemon_behind(tmp_path: Path) -> None:
    # The helper exits within a millisecond of starting; its double-forked child must
    # still be found and killed, every time.
    skill, script = make_skill(tmp_path, "daemon", "( sleep 300 & echo $! > child.pid )\n")
    for _ in range(5):
        out = run_script_scoped(skill, script)
        child = int((skill.path / "child.pid").read_text())
        assert [m.pid for m in out.leaked] == [child]
        assert wait_until_dead(child)


@pytest.mark.usefixtures("needs_scope")
def test_process_hidden_in_a_sub_cgroup_is_found_and_killed(tmp_path: Path) -> None:
    body = (
        "cg=/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup)\n"
        'mkdir "$cg/hide"\n'
        '( sleep 300 & echo $! > "$cg/hide/cgroup.procs"; echo $! > child.pid )\n'
        "sleep 0.2\n"
    )
    skill, script = make_skill(tmp_path, "hider", body)
    out = run_script_scoped(skill, script)
    child = int((skill.path / "child.pid").read_text())
    assert out.result.returncode == 0, out.result.stderr
    assert child in [m.pid for m in out.leaked]
    assert wait_until_dead(child)
    assert wait_until_gone(out.cgroup)


@pytest.mark.usefixtures("needs_scope")
def test_timeout_reports_no_leak_and_keeps_output(tmp_path: Path) -> None:
    skill, script = make_skill(tmp_path, "slow", "echo started\nsleep 300 &\nsleep 300\n")
    out = run_script_scoped(skill, script, timeout=1.0)
    assert out.result.returncode == 124
    assert out.result.stdout == "started\n"
    assert out.result.stderr == "timeout after 1.0s"
    assert out.leaked == ()
    assert len([m for m in out.members if m.comm == "sleep"]) == 2


@pytest.mark.usefixtures("needs_scope")
def test_non_utf8_output_and_comm_do_not_crash(tmp_path: Path) -> None:
    body = (
        "printf '\\377\\376 ok\\n'\n"
        "cp /usr/bin/sleep \"$HOME/$(printf 'bad\\377name')\"\n"
        "\"$HOME/$(printf 'bad\\377name')\" 0.3\n"
    )
    skill, script = make_skill(tmp_path, "binary", body)
    out = run_script_scoped(skill, script)
    assert out.result.returncode == 0, out.result.stderr
    assert out.result.stdout == "\ufffd\ufffd ok\n"
    assert any(m.comm == "bad\ufffdname" for m in out.members)


@pytest.mark.usefixtures("needs_scope")
def test_relative_skill_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_skill(tmp_path / "skills", "rel", 'basename "$PWD"\n')
    monkeypatch.chdir(tmp_path)
    skill = discover_skills(Path("skills"))[0]
    out = run_script_scoped(skill, skill.helper_scripts[0])
    assert out.result.returncode == 0, out.result.stderr
    assert out.result.stdout == "rel\n"


@pytest.mark.usefixtures("needs_scope")
def test_scope_failure_is_not_reported_as_a_helper_result(tmp_path: Path) -> None:
    skill, script = make_skill(tmp_path, "twice", "touch ran-$1\nsleep 2\n")
    first: list[object] = []
    worker = threading.Thread(
        target=lambda: first.append(
            run_script_scoped(skill, script, args=("first",), invocation_id="inv-same")
        )
    )
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while not (skill.path / "ran-first").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        with pytest.raises(ScopeError, match="cim-skill-twice-inv-same.scope"):
            run_script_scoped(skill, script, args=("second",), invocation_id="inv-same")
    finally:
        worker.join()
    assert not (skill.path / "ran-second").exists()  # the refused helper never started
    assert len(first) == 1
