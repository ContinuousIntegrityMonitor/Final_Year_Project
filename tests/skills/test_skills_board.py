"""Skills read model for the status board (U1)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from cim.common.schema.skills import Egress, SkillBehaviourPayload
from cim.common.store import BaselineStore
from cim.skills.__main__ import main
from cim.skills.board import (
    LIST_LIMIT,
    as_dict,
    is_skill_payload,
    rail_label,
    skills_board,
)
from cim.skills.envelope import WARMUP
from cim.skills.inventory import append_event, known_skills, sweep, take_inventory, write_baselines

TS = "2026-11-24T10:00:00Z"
LATER = "2026-11-24T10:01:00Z"


def make_skill(root: Path, name: str) -> Path:
    skill = root / name
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test skill {name}\n---\n", encoding="utf-8"
    )
    (skill / "scripts" / "run.sh").write_text("echo run\n", encoding="utf-8")
    return skill


@pytest.fixture
def root(tmp_path: Path) -> Path:
    skills = tmp_path / "skills"
    for name in ("alpha", "beta", "gamma"):
        make_skill(skills, name)
    return skills


@pytest.fixture
def store(tmp_path: Path, root: Path) -> Iterator[BaselineStore]:
    with BaselineStore(tmp_path / "store.sqlite") as opened:
        write_baselines(opened, take_inventory([root]), ts=TS)
        yield opened


def run(store: BaselineStore, skill_id: str, n: int, *, egress: bool = False) -> None:
    payload = SkillBehaviourPayload(
        skill_id=skill_id,
        invocation_id=f"inv-{n:04d}",
        cgroup_id=f"cim-skill-{skill_id}-inv-{n:04d}.scope",
        binaries_executed=["/usr/bin/bash"],
        file_write_targets=["~"] if n % 2 else [],
        egress=[Egress(dest_class="private_ip", port=9)] if egress else [],
        process_count=1 + n % 3,
        duration_us=1000 + n,
    )
    append_event(store, known_skills(store)[skill_id].artefact_id, "behaviour", payload, LATER)


def add_mcp_records(store: BaselineStore) -> None:
    """What the proxy writes to the same store: a pin, a schema change, a call, an alert."""
    server = store.append_artefact("mcp_server", "hexstrike", "vm-mon")
    store.append_record(
        server, "artefact", {"code": "mcp_pin", "server_id": "hexstrike", "tools": []}, TS
    )
    store.append_record(
        server, "integrity", {"server_id": "hexstrike", "tool_id": "nmap", "path": "x"}, TS
    )
    store.append_record(
        server,
        "behaviour",
        {"server_id": "hexstrike", "tool_id": "nmap", "outcome": "ok", "duration_us": 5},
        TS,
    )
    store.append_record(
        server, "alert", {"code": "mcp_behaviour_drift", "server_id": "hexstrike"}, TS
    )


def board_of(store: BaselineStore) -> dict[str, object]:
    return as_dict(skills_board(store.read_records()))


def row(board: dict[str, object], skill_id: str) -> dict[str, object]:
    rows = board["skills"]
    assert isinstance(rows, list)
    return next(r for r in rows if r["skill_id"] == skill_id)


def test_empty_store_gives_an_empty_section(tmp_path: Path) -> None:
    with BaselineStore(tmp_path / "empty.sqlite") as opened:
        board = board_of(opened)
    assert board["skills"] == [] and board["changes"] == [] and board["runs"] == []
    assert board["summary"] == {
        "skills": 0,
        "healthy": 0,
        "learning": 0,
        "warning": 0,
        "changed": 0,
        "removed": 0,
        "changes": 0,
        "runs": 0,
        "alerts": 0,
    }


def test_shape_is_stable(store: BaselineStore) -> None:
    """The page codes against these keys; changing them is a version bump, not an accident."""
    board = board_of(store)
    assert list(board) == [
        "version",
        "warmup",
        "window",
        "summary",
        "skills",
        "changes",
        "runs",
        "alerts",
    ]
    assert list(row(board, "alpha")) == [
        "skill_id",
        "name",
        "description",
        "root",
        "state",
        "alerts",
        "integrity",
        "behaviour",
    ]
    assert board["version"] == 1 and board["warmup"] == WARMUP


def test_baselined_skill_that_never_ran_is_learning_not_healthy(store: BaselineStore) -> None:
    alpha = row(board_of(store), "alpha")
    assert alpha["state"] == "learning"
    assert alpha["integrity"] == {
        "state": "unchanged",
        "baseline_record_id": 1,
        "baseline_ts": TS,
        "baseline_files": 2,
        "tree_digest": alpha["integrity"]["tree_digest"],  # type: ignore[index]
        "files_now": 2,
        "changes": 0,
        "changed_paths": [],
        "last_change_ts": "",
    }
    assert alpha["behaviour"]["state"] == "empty"  # type: ignore[index]
    assert alpha["name"] == "alpha" and alpha["description"] == "test skill alpha"


def test_edited_file_makes_the_skill_a_warning_once(store: BaselineStore, root: Path) -> None:
    (root / "alpha" / "scripts" / "run.sh").write_text("echo run; curl x\n", encoding="utf-8")
    sweep(store, [root], ts=LATER)
    sweep(store, [root], ts=LATER)  # nothing new: the change is not counted twice
    board = board_of(store)
    alpha = row(board, "alpha")
    assert alpha["state"] == "warning"
    assert alpha["integrity"]["state"] == "changed"  # type: ignore[index]
    assert alpha["integrity"]["changed_paths"] == ["scripts/run.sh"]  # type: ignore[index]
    assert alpha["integrity"]["last_change_ts"] == LATER  # type: ignore[index]
    assert board["changes"] == [
        {
            "record_id": 4,
            "ts": LATER,
            "skill_id": "alpha",
            "change": "modify",
            "path": "scripts/run.sh",
            "old_path": None,
            "old_sha256": board["changes"][0]["old_sha256"],  # type: ignore[index]
            "new_sha256": board["changes"][0]["new_sha256"],  # type: ignore[index]
        }
    ]
    assert row(board, "beta")["state"] == "learning"
    assert board["summary"]["warning"] == 1 and board["summary"]["changed"] == 1  # type: ignore[index]


def test_removed_skill_is_reported_as_removed(store: BaselineStore, root: Path) -> None:
    for path in sorted((root / "gamma").rglob("*"), reverse=True):
        path.rmdir() if path.is_dir() else path.unlink()
    (root / "gamma").rmdir()
    sweep(store, [root], ts=LATER)
    gamma = row(board_of(store), "gamma")
    assert gamma["state"] == "warning"
    assert gamma["integrity"]["state"] == "removed"  # type: ignore[index]
    assert gamma["integrity"]["files_now"] == 0  # type: ignore[index]


def test_behaviour_learns_then_warms_up(store: BaselineStore) -> None:
    for n in range(WARMUP - 1):
        run(store, "beta", n)
    beta = row(board_of(store), "beta")
    assert beta["state"] == "learning"
    assert beta["behaviour"]["state"] == "learning"  # type: ignore[index]
    assert beta["behaviour"]["observations"] == WARMUP - 1  # type: ignore[index]
    run(store, "beta", WARMUP, egress=True)
    beta = row(board_of(store), "beta")
    assert beta["state"] == "healthy"
    behaviour = beta["behaviour"]
    assert isinstance(behaviour, dict)
    assert behaviour["warmed_up"] and behaviour["runs"] == WARMUP
    assert behaviour["binaries"] == [{"value": "/usr/bin/bash", "runs": WARMUP}]
    assert behaviour["destinations"] == [{"value": "private_ip:9", "runs": 1}]
    assert behaviour["processes"] == {"min": 1, "max": 3}


def test_lists_are_newest_first_and_capped(store: BaselineStore) -> None:
    for n in range(LIST_LIMIT + 5):
        run(store, "alpha", n)
    board = board_of(store)
    runs = board["runs"]
    assert isinstance(runs, list)
    assert len(runs) == LIST_LIMIT
    assert runs[0]["invocation_id"] == f"inv-{LIST_LIMIT + 4:04d}"
    assert board["summary"]["runs"] == LIST_LIMIT + 5  # type: ignore[index]
    assert row(board, "alpha")["behaviour"]["runs"] == LIST_LIMIT + 5  # type: ignore[index]


def test_skill_alert_is_listed_and_makes_a_warning(store: BaselineStore) -> None:
    aid = known_skills(store)["alpha"].artefact_id
    store.append_record(
        aid, "alert", {"code": "skill_behaviour_drift", "skill_id": "alpha", "detail": "new"}, TS
    )
    board = board_of(store)
    assert row(board, "alpha")["state"] == "warning"
    assert row(board, "alpha")["alerts"] == 1
    assert board["alerts"] == [
        {
            "record_id": 4,
            "ts": TS,
            "skill_id": "alpha",
            "code": "skill_behaviour_drift",
            "detail": "new",
        }
    ]


def test_mcp_records_in_the_same_store_are_left_out(store: BaselineStore) -> None:
    before = board_of(store)
    add_mcp_records(store)
    assert board_of(store) == before


def test_is_skill_payload_splits_a_shared_store_cleanly(store: BaselineStore, root: Path) -> None:
    """U1: in a store both sides write, each record is claimed by exactly one side."""
    (root / "alpha" / "SKILL.md").write_text("changed\n", encoding="utf-8")
    sweep(store, [root], ts=LATER)
    run(store, "alpha", 1)
    add_mcp_records(store)
    skills, mcp = set(), set()
    for record in store.read_records():
        payload = json.loads(record.payload)
        (skills if is_skill_payload(payload) else mcp).add(record.kind)
        assert is_skill_payload(payload) != ("server_id" in payload)
    assert skills == {"artefact", "integrity", "behaviour"}
    assert mcp == {"artefact", "integrity", "behaviour", "alert"}
    assert not is_skill_payload(None) and not is_skill_payload({"skill_id": 3})


def test_board_without_the_wiring_still_mislabels_skill_records(
    store: BaselineStore, root: Path
) -> None:
    """Documents U1 until `load_board` calls `rail_label` (docs/U1_SKILLS_BOARD_SHAPE.md).

    Once the board carries a skills section this test skips itself: delete it then.
    """
    from cim.dashboard.board import load_board

    (root / "alpha" / "SKILL.md").write_text("changed\n", encoding="utf-8")
    sweep(store, [root], ts=LATER)
    run(store, "alpha", 1)
    board = load_board(store.path)
    if getattr(board, "skills", None) is not None:
        pytest.skip("the board is wired: U1 is fixed; delete this test")
    assert [c.tool for c in board.calls] == ["unknown"]
    assert [c.server_id for c in board.changes] == [""]


def test_rail_labels() -> None:
    assert rail_label("integrity", {"skill_id": "a", "change": "modify", "path": "SKILL.md"}) == (
        "change",
        "a: modify SKILL.md",
    )
    assert rail_label("behaviour", {"skill_id": "a"}) == ("call", "a: run")
    assert rail_label("artefact", {"skill_id": "a"}) == ("baseline", "a: baseline")
    assert rail_label("alert", {"skill_id": "a", "detail": "new binary"}) == (
        "alert",
        "a: new binary",
    )
    assert rail_label("behaviour", {"server_id": "hexstrike"}) is None


def test_cli_text_and_json(
    store: BaselineStore, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (root / "alpha" / "SKILL.md").write_text("changed\n", encoding="utf-8")
    sweep(store, [root], ts=LATER)
    assert main(["board", "--db", str(store.path)]) == 0
    text = capsys.readouterr().out.splitlines()
    assert text[0].startswith("skills: 3 installed, 1 warning, 2 learning, 0 healthy")
    assert "alpha: warning | files changed (SKILL.md) | behaviour no runs (0/30)" in text
    assert main(["board", "--db", str(store.path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["skills"] == 3


def test_cli_does_not_create_a_missing_store(tmp_path: Path) -> None:
    missing = tmp_path / "none.sqlite"
    assert main(["board", "--db", str(missing)]) == 2
    assert not missing.exists()
