"""Unit tests for the skill runner (T-05)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from cim.skills.runner import discover_skills, parse_frontmatter, run_script


def make_skill(root: Path, name: str, script_body: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: demo skill {name}\n---\n# {name}\n",
        encoding="utf-8",
    )
    (skill_dir / "helper.py").write_text(script_body, encoding="utf-8")
    return skill_dir


def test_parse_frontmatter() -> None:
    meta = parse_frontmatter('---\nname: a\ndescription: "b c"\n---\nbody')
    assert meta == {"name": "a", "description": "b c"}


def test_parse_frontmatter_missing() -> None:
    assert parse_frontmatter("no frontmatter here") == {}


def test_discover_skills(tmp_path: Path) -> None:
    make_skill(tmp_path, "alpha", "print('hi')\n")
    make_skill(tmp_path, "beta", "print('yo')\n")
    (tmp_path / "not-a-skill").mkdir()
    skills = discover_skills(tmp_path)
    assert [s.skill_id for s in skills] == ["alpha", "beta"]
    assert skills[0].description == "demo skill alpha"
    assert [p.name for p in skills[0].helper_scripts] == ["helper.py"]


def test_run_script_uses_clean_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIM_SECRET_TEST", "leak")
    body = "import os\nprint(os.environ.get('CIM_SECRET_TEST', 'clean'))\n"
    make_skill(tmp_path, "alpha", body)
    skill = discover_skills(tmp_path)[0]
    result = run_script(skill, skill.helper_scripts[0])
    assert result.returncode == 0
    assert result.stdout.strip() == "clean"


def test_run_script_passes_args(tmp_path: Path) -> None:
    make_skill(tmp_path, "alpha", "import sys\nprint(sys.argv[1])\n")
    skill = discover_skills(tmp_path)[0]
    result = run_script(skill, skill.helper_scripts[0], args=("hello",))
    assert result.stdout.strip() == "hello"


def wait_until_dead(pid: int, seconds: float = 3.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not Path(f"/proc/{pid}").exists():
            return True
        time.sleep(0.05)
    return not Path(f"/proc/{pid}").exists()


def test_parse_frontmatter_ignores_bom() -> None:
    assert parse_frontmatter("\ufeff---\nname: a\n---\n") == {"name": "a"}


def test_parse_frontmatter_block_and_continuation_values() -> None:
    text = (
        "---\n"
        "name: a\n"
        "description: >-\n  folded text\n  more\n"
        "notes: |\n  line one\n  line two\n"
        "summary: starts here\n  and continues\n"
        "---\n"
    )
    assert parse_frontmatter(text) == {
        "name": "a",
        "description": "folded text more",
        "notes": "line one\nline two",
        "summary": "starts here and continues",
    }


def test_parse_frontmatter_skips_nested_structures() -> None:
    text = "---\nmetadata:\n  author: someone\nname: a\n---\n"
    assert parse_frontmatter(text) == {"metadata": "", "name": "a"}


def test_parse_frontmatter_strips_only_matching_quotes() -> None:
    meta = parse_frontmatter("---\na: 'x y'\nb: \"it's\"\nc: 5\" disk\n---\n")
    assert meta == {"a": "x y", "b": "it's", "c": '5" disk'}


def test_discover_survives_undecodable_manifest(tmp_path: Path) -> None:
    make_skill(tmp_path, "alpha", "print('hi')\n")
    broken = make_skill(tmp_path, "broken", "print('hi')\n")
    (broken / "SKILL.md").write_bytes(b"---\nname: \xff\xfe\n---\n")
    assert [s.skill_id for s in discover_skills(tmp_path)] == ["alpha", "broken"]


def test_empty_frontmatter_name_falls_back_to_directory(tmp_path: Path) -> None:
    skill_dir = make_skill(tmp_path, "alpha", "print('hi')\n")
    (skill_dir / "SKILL.md").write_text("---\nname:\n---\n", encoding="utf-8")
    assert discover_skills(tmp_path)[0].name == "alpha"


def test_run_script_with_relative_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_skill(tmp_path / "skills", "alpha", "import os\nprint(os.path.basename(os.getcwd()))\n")
    monkeypatch.chdir(tmp_path)
    skill = discover_skills(Path("skills"))[0]
    result = run_script(skill, skill.helper_scripts[0])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "alpha"


def test_run_script_tolerates_non_utf8_output(tmp_path: Path) -> None:
    body = "import sys\nsys.stdout.buffer.write(b'\\xff\\xfe ok\\n')\n"
    make_skill(tmp_path, "alpha", body)
    skill = discover_skills(tmp_path)[0]
    result = run_script(skill, skill.helper_scripts[0])
    assert result.returncode == 0
    assert result.stdout == "\ufffd\ufffd ok\n"


def test_run_script_does_not_inherit_stdin(tmp_path: Path) -> None:
    make_skill(tmp_path, "alpha", "import sys\nprint(repr(sys.stdin.read()))\n")
    skill = discover_skills(tmp_path)[0]
    assert run_script(skill, skill.helper_scripts[0]).stdout.strip() == "''"


def test_run_script_rejects_unsupported_suffix(tmp_path: Path) -> None:
    make_skill(tmp_path, "alpha", "print('hi')\n")
    skill = discover_skills(tmp_path)[0]
    with pytest.raises(ValueError):
        run_script(skill, tmp_path / "alpha" / "helper.rb")


def test_run_script_timeout_kills_children_and_keeps_output(tmp_path: Path) -> None:
    skill_dir = make_skill(tmp_path, "alpha", "")
    (skill_dir / "run.sh").write_text("echo started\nsleep 300 &\necho $! > child.pid\nwait\n")
    skill = discover_skills(tmp_path)[0]
    start = time.monotonic()
    result = run_script(skill, skill_dir / "run.sh", timeout=1.0)
    assert time.monotonic() - start < 10
    assert result.returncode == 124
    assert result.stdout == "started\n"
    assert result.stderr == "timeout after 1.0s"
    assert wait_until_dead(int((skill_dir / "child.pid").read_text()))


def test_run_script_kills_background_children_after_exit(tmp_path: Path) -> None:
    skill_dir = make_skill(tmp_path, "alpha", "")
    (skill_dir / "run.sh").write_text("sleep 300 &\necho $! > child.pid\n")
    skill = discover_skills(tmp_path)[0]
    start = time.monotonic()
    result = run_script(skill, skill_dir / "run.sh")
    assert result.returncode == 0
    assert time.monotonic() - start < 10  # did not wait for the background child
    assert wait_until_dead(int((skill_dir / "child.pid").read_text()))


def test_python_helpers_leave_no_bytecode_behind(tmp_path: Path) -> None:
    skill_dir = make_skill(tmp_path, "alpha", "import sibling\nprint(sibling.VALUE)\n")
    (skill_dir / "sibling.py").write_text("VALUE = 7\n", encoding="utf-8")
    skill = discover_skills(tmp_path)[0]
    result = run_script(skill, skill_dir / "helper.py")
    assert result.stdout.strip() == "7", result.stderr
    assert not (skill_dir / "__pycache__").exists()
