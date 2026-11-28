"""`cim status` (C5) and `cim events` (T-13, design note section 7)."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from cim.cli import app
from cim.common.schema.alerts import MonitorAlertPayload
from cim.common.schema.mcp import McpBehaviourPayload
from cim.common.schema.skills import Egress, SkillBehaviourPayload
from cim.common.status import events, load_status, select
from cim.common.store import BaselineStore
from cim.mcp.events import append_mcp
from cim.skills.alert import score_run
from cim.skills.corpus import default_root
from cim.skills.inventory import append_event, known_skills

runner = CliRunner()
TS = "2026-11-25T12:00:00Z"
DIGEST = "a" * 64


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    """Two seed skills and a two-tool MCP server, inventoried. Returns (config, store)."""
    for name in ("word-count", "csv-summary"):
        shutil.copytree(default_root() / name, tmp_path / "skills" / name)
    _tools(tmp_path, {"a": "a tool", "b": "b tool"})
    config = tmp_path / "cim.toml"
    config.write_text(
        '[store]\npath = "store.sqlite"\n[skills]\nroots = ["skills"]\n'
        '[mcp.servers.srv]\ntools_list = "tools.json"\nminimum_tools = 1\n',
        encoding="utf-8",
    )
    result = runner.invoke(app, ["inventory", "--config", str(config)])
    assert result.exit_code == 0, result.output
    return config, tmp_path / "store.sqlite"


def _tools(tmp_path: Path, tools: dict[str, str]) -> None:
    listed = [{"name": n, "description": d, "inputSchema": {}} for n, d in tools.items()]
    (tmp_path / "tools.json").write_text(json.dumps({"tools": listed}), encoding="utf-8")


def _status(config: Path) -> tuple[int, dict[str, Any]]:
    result = runner.invoke(app, ["status", "--config", str(config), "--json"])
    return result.exit_code, json.loads(result.output)


def _call(store: BaselineStore, n: int) -> None:
    tool_aid = store.get_or_create_artefact("mcp_tool", "a", "test")
    payload = McpBehaviourPayload(
        server_id="srv",
        tool_id="a",
        invocation_id=f"s:{n}",
        request_digest=DIGEST,
        binaries_executed=[],
        file_write_targets=[],
        egress=[],
        process_count=0,
        duration_us=1,
        outcome="ok",
    )
    append_mcp(
        store,
        tool_aid,
        artefact_type="mcp_tool",
        server_id="srv",
        tool_id="a",
        kind="behaviour",
        payload=payload,
        ts=TS,
    )


def _run(store: BaselineStore, n: int, egress: tuple[Egress, ...] = ()) -> int:
    aid = known_skills(store)["word-count"].artefact_id
    run = SkillBehaviourPayload(
        skill_id="word-count",
        invocation_id=f"inv-{n}",
        cgroup_id=f"cim-skill-word-count-inv-{n}.scope",
        binaries_executed=["/usr/bin/python3"],
        file_write_targets=[],
        egress=list(egress),
        process_count=1,
        duration_us=1,
    )
    record_id = append_event(store, aid, "behaviour", run, TS)
    score_run(store, artefact_id=aid, skill_id="word-count", record_id=record_id, ts=TS)
    return record_id


def test_a_clean_store_is_clean(tmp_path: Path) -> None:
    """Design section 8: benign operations give the inventory and zero findings."""
    config, db = _setup(tmp_path)
    with BaselineStore(db) as store:
        for n in range(3):
            _call(store, n)
            _run(store, n)
    code, shown = _status(config)
    assert code == 0
    assert shown["chain"]["ok"] is True and shown["chain"]["hash_version"] == 2
    assert shown["inventory"] == {"mcp": {"servers": 1, "tools": 2}, "skills": 2}
    assert shown["findings"] == []
    assert shown["behaviour_alerts"] == {"skills": 0, "mcp": 0}
    assert (shown["monitor_events"], shown["capture_faults"]) == (0, 0)
    assert shown["learning"] == {"mcp_tools": 2, "skills": 2, "warmup": 30}
    assert shown["clean"] is True
    assert shown["collectors"] == {
        "supervised": False,
        "watch": None,
        "sessions": [],
        "ended_without_closing": [],
    }


def test_one_tampered_skill_is_one_finding(tmp_path: Path) -> None:
    """Design section 8: one tampered artefact is exactly one finding, with all its changes."""
    config, _db = _setup(tmp_path)
    skill = tmp_path / "skills" / "word-count"
    (skill / "SKILL.md").write_text("changed\n", encoding="utf-8")
    (skill / "scripts" / "count.py").write_text("print('x')\n", encoding="utf-8")
    runner.invoke(app, ["sweep", "--config", str(config)])
    code, shown = _status(config)
    assert code == 1 and shown["clean"] is False
    assert [(f["side"], f["artefact"]) for f in shown["findings"]] == [
        ("skills", "skill word-count")
    ]
    assert sorted(shown["findings"][0]["changes"]) == [
        "modify SKILL.md",
        "modify scripts/count.py",
    ]


def test_a_rug_pull_on_one_tool_is_one_finding(tmp_path: Path) -> None:
    config, _db = _setup(tmp_path)
    _tools(tmp_path, {"a": "now does something else", "b": "b tool", "c": "new"})
    runner.invoke(app, ["sweep", "--config", str(config)])
    code, shown = _status(config)
    assert code == 1
    assert sorted(f["artefact"] for f in shown["findings"]) == ["mcp srv/a", "mcp srv/c"]
    lines = runner.invoke(app, ["status", "--config", str(config)]).output.splitlines()
    assert lines[3] == "findings   2 changed artefacts:"
    assert any("mcp srv/a (description changed, " in line for line in lines)


def test_alerts_and_faults_are_counted(tmp_path: Path) -> None:
    config, db = _setup(tmp_path)
    with BaselineStore(db) as store:
        for n in range(30):
            _run(store, n)
        _run(store, 99, egress=(Egress(dest_class="public_ip", port=443),))
        server = store.get_or_create_artefact("mcp_server", "srv", "test")
        append_mcp(
            store,
            server,
            artefact_type="mcp_server",
            server_id="srv",
            kind="alert",
            payload={"code": "proxy_capture_failed", "reason": "x", "stage": "store"},
            ts=TS,
        )
        monitor = store.append_artefact("monitor", "skills-watcher", "test")
        restarted = MonitorAlertPayload(
            code="collector_restarted",
            reason="exited",
            component="skills-watcher",
            exit_code=-9,
            gap_s=1,
            restarts=1,
        )
        store.append_record(monitor, "alert", restarted.model_dump(mode="json"), TS)
    code, shown = _status(config)
    assert code == 1
    assert shown["behaviour_alerts"] == {"skills": 1, "mcp": 0}
    assert (shown["monitor_events"], shown["capture_faults"]) == (1, 1)
    assert shown["findings"] == []
    assert shown["learning"]["skills"] == 1  # csv-summary has no runs; word-count is warm


def test_a_broken_chain_is_reported(tmp_path: Path) -> None:
    config, db = _setup(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE record SET payload = '{}' WHERE id = 2")
    con.commit()
    con.close()
    result = runner.invoke(app, ["status", "--config", str(config)])
    assert result.exit_code == 1
    assert "CHAIN BROKEN at record 2" in result.output


def test_status_needs_a_store(tmp_path: Path) -> None:
    result = runner.invoke(app, ["status", "--db", str(tmp_path / "none.sqlite")])
    assert result.exit_code == 2 and "no store at" in result.output
    assert not (tmp_path / "none.sqlite").exists()


def test_events_word_each_side(tmp_path: Path) -> None:
    config, db = _setup(tmp_path)
    with BaselineStore(db) as store:
        _call(store, 1)
        _run(store, 1)
        monitor = store.append_artefact("monitor", "skills-watcher", "test")
        failed = MonitorAlertPayload(
            code="collector_failed",
            reason="gave_up",
            component="skills-watcher",
            gap_s=60,
            restarts=5,
        )
        store.append_record(monitor, "alert", failed.model_dump(mode="json"), TS)
        artefacts = {item.id: item for item in store.read_artefacts()}
        found = events(store.read_records(), artefacts)
        server = store.get_or_create_artefact("mcp_server", "srv", "test")
        append_mcp(
            store,
            server,
            artefact_type="mcp_server",
            server_id="srv",
            kind="alert",
            payload={"code": "proxy_malformed_frame", "reason": "not_json"},
            ts=TS,
        )
        artefacts = {item.id: item for item in store.read_artefacts()}
        last = events(store.read_records(), artefacts)[-1]
    assert (last.side, last.label) == ("mcp", "srv: proxy_malformed_frame (not_json)")
    labels = {(e.side, e.kind, e.label) for e in found}
    assert ("skills", "artefact", "word-count: baseline") in labels
    assert ("mcp", "artefact", "srv: baseline (2 tools)") in labels
    assert ("mcp", "artefact", "srv: fingerprint pinned") in labels
    assert ("mcp", "behaviour", "srv/a: call ok") in labels
    assert ("skills", "behaviour", "word-count: run") in labels
    assert ("monitor", "alert", "skills-watcher: collector_failed (gave_up)") in labels
    assert [e.record_id for e in found] == sorted(e.record_id for e in found)

    shown = runner.invoke(app, ["events", "--config", str(config), "--side", "mcp", "--last", "2"])
    assert shown.exit_code == 0
    assert len(shown.output.splitlines()) == 2
    assert all(" mcp " in line for line in shown.output.splitlines())
    only = runner.invoke(app, ["events", "--config", str(config), "--kind", "behaviour", "--json"])
    rows = [json.loads(line) for line in only.output.splitlines()]
    assert {row["kind"] for row in rows} == {"behaviour"} and len(rows) == 2


def test_select_filters() -> None:
    from cim.common.status import Event

    found = [
        Event(1, "2026-11-24T10:00:00Z", "skills", "artefact", "a"),
        Event(2, "2026-11-25T09:00:00Z", "mcp", "alert", "b"),
        Event(3, "2026-11-25T11:00:00Z", "skills", "integrity", "c"),
    ]
    assert [e.record_id for e in select(found, since="2026-11-25")] == [2, 3]
    assert [e.record_id for e in select(found, since="2026-11-25T10")] == [3]
    assert [e.record_id for e in select(found, side="skills", last=1)] == [3]
    assert [e.record_id for e in select(found, kinds=["alert", "artefact"])] == [1, 2]
    assert found[0].render() == "#1 2026-11-24T10:00:00Z skills  artefact  a"


def test_load_status_reads_the_store_once(tmp_path: Path) -> None:
    _config, db = _setup(tmp_path)
    status = load_status(db)
    assert status.clean and status.records > 0 and status.tip is not None


def test_read_artefacts_lists_every_row(tmp_path: Path) -> None:
    with BaselineStore(tmp_path / "s.sqlite") as store:
        first = store.append_artefact("skill", "word-count", "laptop")
        second = store.append_artefact("mcp_server", "srv", "vm-mon")
        found = store.read_artefacts()
    assert [(a.id, a.type, a.name, a.origin) for a in found] == [
        (first, "skill", "word-count", "laptop"),
        (second, "mcp_server", "srv", "vm-mon"),
    ]


def test_events_follow_prints_new_records(tmp_path: Path, monkeypatch: Any) -> None:
    import cim.cli as cli

    config, db = _setup(tmp_path)
    ticks = {"n": 0}

    def tick(_seconds: float) -> None:
        ticks["n"] += 1
        if ticks["n"] == 1:
            with BaselineStore(db) as store:
                _call(store, 7)
            return
        raise KeyboardInterrupt

    monkeypatch.setattr(cli.time, "sleep", tick)
    result = runner.invoke(app, ["events", "--config", str(config), "--last", "1", "--follow"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert len(lines) == 2 and lines[-1].endswith("srv/a: call ok")


def test_an_mcp_behaviour_alert_is_counted(tmp_path: Path) -> None:
    """The alert as score_latest writes it: BehaviourAlertPayload, with "skill_id": null."""
    from cim.common.schema.alerts import BehaviourAlertPayload, DriftFeature

    config, db = _setup(tmp_path)
    with BaselineStore(db) as store:
        _call(store, 1)
        server = store.get_or_create_artefact("mcp_server", "srv", "test")
        alert = BehaviourAlertPayload(
            code="mcp_behaviour_drift",
            server_id="srv",
            tool_id="a",
            observation_record_id=store.read_records()[-1].id,
            composite_milli=10_000,
            features=[
                DriftFeature(
                    feature="value_class",
                    how="never_seen",
                    values=["private_ip"],
                    score_milli=10_000,
                    threshold_milli=4000,
                )
            ],
            window=100,
            scorer_version=1,
            detail="a changed how it is used: value class private_ip",
        )
        append_mcp(
            store,
            server,
            artefact_type="mcp_server",
            server_id="srv",
            kind="alert",
            payload=alert,
            ts=TS,
        )
        assert json.loads(store.read_records()[-1].payload)["skill_id"] is None
        found = events(store.read_records(), {a.id: a for a in store.read_artefacts()})
    code, shown = _status(config)
    assert code == 1 and shown["behaviour_alerts"] == {"skills": 0, "mcp": 1}
    assert found[-1].label == (
        "srv/a: mcp_behaviour_drift: a changed how it is used: value class private_ip"
    )
