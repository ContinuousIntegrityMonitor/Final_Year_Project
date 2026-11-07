"""Unit tests for the skill runner (T-05)."""

from __future__ import annotations

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
