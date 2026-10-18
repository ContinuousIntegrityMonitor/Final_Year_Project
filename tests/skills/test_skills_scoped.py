"""Per-invocation cgroup scope tests (T-05). Live tests need a systemd user session."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from cim.skills.runner import Skill, discover_skills
from cim.skills.scoped import (
    CGROUP_ROOT,
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
