"""The shared `cim` CLI after the T-13 restructure (design note section 5, decision 5)."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from cim.cli import app
from cim.common.config import parse_config
from cim.common.schema.skills import SkillBehaviourPayload
from cim.common.store import BaselineStore
from cim.mcp.envelope import record_observation
from cim.skills.corpus import default_root
from cim.skills.inventory import append_event, known_skills

runner = CliRunner()
TS = "2026-11-25T12:00:00Z"


def _skills(tmp_path: Path, *names: str) -> Path:
    root = tmp_path / "skills"
    for name in names:
        shutil.copytree(default_root() / name, root / name)
    return root


def _tools(tmp_path: Path, *names: str) -> Path:
    path = tmp_path / "tools.json"
    tools = [{"name": n, "description": f"{n} tool", "inputSchema": {}} for n in names]
    path.write_text(json.dumps({"tools": tools}), encoding="utf-8")
    return path


def _config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cim.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _both_sides(tmp_path: Path) -> Path:
    """A cim.toml naming a skill root and one MCP server with a tools list."""
    _skills(tmp_path, "word-count", "csv-summary")
    _tools(tmp_path, "a", "b")
    return _config(
        tmp_path,
        '[store]\npath = "logs/store.sqlite"\norigin = "laptop"\n'
        '[skills]\nroots = ["skills"]\n'
        '[mcp.servers.srv]\nroot = "/opt/srv"\ntools_list = "tools.json"\nminimum_tools = 1\n',
    )


def _kinds(db: Path) -> list[tuple[str, str]]:
    con = sqlite3.connect(db)
    try:
        return [(str(t), str(n)) for t, n in con.execute("SELECT type, name FROM artefact")]
    finally:
        con.close()


def test_help_lists_both_sides_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in (
        "version",
        "init",
        "inventory",
        "sweep",
        "envelope",
        "status",
        "verify-chain",
        "dashboard",
        "proxy",
        "http-gateway",
        "skills",
    ):
        assert command in result.output


def test_init_writes_a_file_the_loader_accepts(tmp_path: Path) -> None:
    target = tmp_path / "etc" / "cim.toml"
    roots = ["--skill-root", str(tmp_path / "a"), "--skill-root", str(tmp_path / "b")]
    result = runner.invoke(app, ["init", str(target), "--origin", "laptop", *roots])
    assert result.exit_code == 0, result.output
    assert "2 skill root(s)" in result.output
    config = parse_config(tomllib.loads(target.read_text(encoding="utf-8")))
    assert config.store.origin == "laptop"
    assert config.skills.roots == (tmp_path / "a", tmp_path / "b")
    again = runner.invoke(app, ["init", str(target)])
    assert again.exit_code == 1 and "pass --force" in again.output
    assert runner.invoke(app, ["init", str(target), "--force"]).exit_code == 0


def test_inventory_covers_both_sides_from_the_config(tmp_path: Path) -> None:
    config = _both_sides(tmp_path)
    result = runner.invoke(app, ["inventory", "--config", str(config)])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0] == "inventory: skills=2 new_baselines=2 chain=ok"
    assert result.output.splitlines()[1].startswith("inventory: server=srv tools=2 ")
    assert "pin=written" in result.output
    db = tmp_path / "logs/store.sqlite"  # [store].path, relative to the file; folder created
    kinds = _kinds(db)
    assert ("skill", "word-count") in kinds and ("mcp_server", "srv") in kinds
    with BaselineStore(db) as store:
        assert store.verify_chain().ok
        assert set(known_skills(store)) == {"word-count", "csv-summary"}


def test_side_limits_inventory_to_one_side(tmp_path: Path) -> None:
    config = _both_sides(tmp_path)
    skills_only = runner.invoke(app, ["inventory", "--config", str(config), "--side", "skills"])
    assert skills_only.output.count("inventory:") == 1 and "skills=2" in skills_only.output
    mcp_only = runner.invoke(app, ["inventory", "--config", str(config), "--side", "mcp"])
    assert mcp_only.output.count("inventory:") == 1 and "server=srv" in mcp_only.output


def test_flags_beat_the_config(tmp_path: Path) -> None:
    config = _both_sides(tmp_path)
    other = tmp_path / "elsewhere.sqlite"
    only = _skills(tmp_path / "flagged", "word-count")
    result = runner.invoke(
        app,
        [
            "inventory",
            "--config",
            str(config),
            "--db",
            str(other),
            "--skill-root",
            str(only),
            "--side",
            "skills",
            "--origin",
            "flagged-host",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "skills=1" in result.output and not (tmp_path / "logs").exists()
    con = sqlite3.connect(other)
    try:
        origins = {str(row[0]) for row in con.execute("SELECT origin FROM artefact")}
    finally:
        con.close()
    assert origins == {"flagged-host"}


def test_the_old_mcp_inventory_call_is_unchanged(tmp_path: Path) -> None:
    listed = _tools(tmp_path, "a")
    db = tmp_path / "s.sqlite"
    args = ["--db", str(db), "--tools-json", str(listed), "--server-id", "srv", "--minimum", "1"]
    result = runner.invoke(app, ["inventory", *args])
    assert result.exit_code == 0, result.output
    assert result.output.count("\n") == 1 and "server=srv tools=1" in result.output
    con = sqlite3.connect(db)
    try:
        row = con.execute("SELECT origin FROM artefact WHERE type = 'mcp_server'").fetchone()
    finally:
        con.close()
    assert row[0] == "vm-mon"  # today's default origin


def test_nothing_to_do_says_what_is_missing(tmp_path: Path) -> None:
    result = runner.invoke(app, ["inventory", "--db", str(tmp_path / "s.sqlite")])
    assert result.exit_code == 2
    assert "no skill roots" in result.output and "no an MCP tools list" not in result.output
    assert "MCP tools list" in result.output
    assert not (tmp_path / "s.sqlite").exists()


def test_a_server_without_a_tools_list_is_refused(tmp_path: Path) -> None:
    config = _config(tmp_path, "[mcp.servers.lab]\n")
    result = runner.invoke(app, ["inventory", "--config", str(config), "--server-id", "lab"])
    assert result.exit_code == 2 and "no tools list for lab" in result.output


def test_a_bad_config_stops_the_command(tmp_path: Path) -> None:
    config = _config(tmp_path, '[mcp.gateway]\naccess_token = "x"\n')
    result = runner.invoke(app, ["inventory", "--config", str(config)])
    assert result.exit_code == 2 and "secrets do not belong" in result.output


def test_sweep_covers_both_sides(tmp_path: Path) -> None:
    config = _both_sides(tmp_path)
    runner.invoke(app, ["inventory", "--config", str(config)])
    clean = runner.invoke(app, ["sweep", "--config", str(config)])
    assert clean.exit_code == 0, clean.output
    assert clean.output == "sweep: skills unchanged\nsweep: srv unchanged\n"
    (tmp_path / "skills/word-count/SKILL.md").write_text("changed\n", encoding="utf-8")
    _tools(tmp_path, "a", "b", "c")
    changed = runner.invoke(app, ["sweep", "--config", str(config)])
    assert changed.output == "sweep: word-count: modify SKILL.md\nsweep: c: tool added\n"


def test_sweep_needs_a_store(tmp_path: Path) -> None:
    config = _both_sides(tmp_path)
    result = runner.invoke(app, ["sweep", "--config", str(config)])
    assert result.exit_code == 2 and "run cim inventory first" in result.output
    assert not (tmp_path / "logs").exists()


def test_envelope_covers_both_sides(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    for _ in range(5):
        record_observation(
            db, server_id="mail", tool="send", arguments={"to": "x"}, result_size=4, outcome="ok"
        )
    with BaselineStore(db) as store:
        aid = store.append_artefact("skill", "word-count", "test")
        run = SkillBehaviourPayload(
            skill_id="word-count",
            invocation_id="inv-1",
            cgroup_id="cim-skill-word-count-inv-1.scope",
            binaries_executed=["/usr/bin/python3"],
            file_write_targets=[],
            egress=[],
            process_count=1,
            duration_us=10,
        )
        append_event(store, aid, "behaviour", run, TS)
    both = runner.invoke(app, ["envelope", "--db", str(db)])
    assert both.exit_code == 0, both.output
    assert "send" in both.output and "warming_up 5/30" in both.output
    assert "word-count: warming_up 1/30" in both.output
    skills_only = runner.invoke(app, ["envelope", "--db", str(db), "--side", "skills"])
    assert "send" not in skills_only.output and "word-count" in skills_only.output
    nothing = runner.invoke(
        app, ["envelope", "--db", str(db), "--skill", "nope", "--side", "skills"]
    )
    assert nothing.exit_code == 2 and "no observations for nope" in nothing.output


def test_cim_skills_forwards_to_the_skills_tools(tmp_path: Path) -> None:
    helped = runner.invoke(app, ["skills", "--help"])
    assert helped.exit_code == 0
    for command in ("corpus", "observe", "exec", "attack", "board"):
        assert command in helped.output
    missing = runner.invoke(app, ["skills", "board", "--db", str(tmp_path / "none.sqlite")])
    assert missing.exit_code == 2
    wrong = runner.invoke(app, ["skills", "no-such-command"])
    assert wrong.exit_code == 2
    verified = runner.invoke(app, ["skills", "corpus", "verify"])
    assert verified.exit_code == 0 and "manifest verifies" in verified.output


def test_verify_chain_reads_the_store_from_the_config(tmp_path: Path) -> None:
    config = _both_sides(tmp_path)
    missing = runner.invoke(app, ["verify-chain", "--config", str(config)])
    assert missing.exit_code == 2 and "no store at" in missing.output
    runner.invoke(app, ["inventory", "--config", str(config)])
    result = runner.invoke(app, ["verify-chain", "--config", str(config)])
    assert result.exit_code == 0 and result.output.startswith("verify-chain: ok (")


def test_help_shows_config_table_names() -> None:
    """Typer's rich help reads [store] as markup unless escaped (verify checklist, 2026-11-27)."""
    shown = runner.invoke(app, ["inventory", "--help"], terminal_width=200).output
    for name in ("[store].path", "[skills].roots", "[mcp.servers.<id>].tools_list"):
        assert name in shown, name
