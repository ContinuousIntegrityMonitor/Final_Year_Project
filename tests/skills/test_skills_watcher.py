"""Skills integrity watcher (T-10): notifications plus periodic sweep, events into the store."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

import cim.skills.watcher as watcher_module
from cim.common.store import BaselineStore
from cim.skills.inventory import SweepResult
from cim.skills.watcher import watch

NEVER = 3600.0  # an interval so long that only a notification can trigger a sweep


def make_skill(root: Path, name: str) -> Path:
    skill = root / name
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    (skill / "scripts" / "run.sh").write_text("echo run\n", encoding="utf-8")
    return skill


@pytest.fixture
def root(tmp_path: Path) -> Path:
    skills = tmp_path / "skills"
    make_skill(skills, "alpha")
    make_skill(skills, "beta")
    return skills


def integrity(db: Path) -> list[tuple[str, str, str]]:
    with BaselineStore(db) as store:
        payloads = [json.loads(r.payload) for r in store.read_records() if r.kind == "integrity"]
    return [(p["skill_id"], p["change"], p["path"]) for p in payloads]


def wait_for(condition: Callable[[], bool], seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


@contextmanager
def running(db: Path, roots: list[Path], **options: object) -> Iterator[list[SweepResult]]:
    """Run the watcher in a thread; yield the sweeps it reports. The first one has finished."""
    sweeps: list[SweepResult] = []
    stop = threading.Event()
    thread = threading.Thread(
        target=watch, args=(db, roots), kwargs={"stop": stop, "report": sweeps.append, **options}
    )
    thread.start()
    try:
        assert wait_for(lambda: len(sweeps) >= 1, 5), "initial sweep did not finish"
        time.sleep(0.3)  # let the notification watches settle
        yield sweeps
    finally:
        stop.set()
        thread.join(5)
        assert not thread.is_alive(), "watcher did not stop"


def test_edit_is_recorded_within_five_seconds_via_notifications(tmp_path: Path, root: Path) -> None:
    db = tmp_path / "store.sqlite"
    with running(db, [root], interval=NEVER):
        started = time.monotonic()
        (root / "alpha" / "scripts" / "run.sh").write_text("echo changed\n", encoding="utf-8")
        assert wait_for(lambda: bool(integrity(db)), 5)
        assert time.monotonic() - started < 5
    assert integrity(db) == [("alpha", "modify", "scripts/run.sh")]


def test_edit_is_found_within_the_interval_without_notifications(
    tmp_path: Path, root: Path
) -> None:
    db = tmp_path / "store.sqlite"
    with running(db, [root], interval=0.3, use_inotify=False):
        (root / "beta" / "SKILL.md").write_text("---\nname: beta\n---\nmore\n", encoding="utf-8")
        assert wait_for(lambda: bool(integrity(db)), 5)
    assert integrity(db) == [("beta", "modify", "SKILL.md")]


def test_reading_files_produces_no_event_and_no_extra_sweep(tmp_path: Path, root: Path) -> None:
    db = tmp_path / "store.sqlite"
    with running(db, [root], interval=NEVER) as sweeps:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                path.read_bytes()
        time.sleep(1.5)
        assert len(sweeps) == 1  # the watcher's own reads do not wake it either
    assert integrity(db) == []


def test_rewriting_identical_content_produces_no_event(tmp_path: Path, root: Path) -> None:
    db = tmp_path / "store.sqlite"
    with running(db, [root], interval=NEVER) as sweeps:
        (root / "alpha" / "scripts" / "run.sh").write_text("echo run\n", encoding="utf-8")
        assert wait_for(lambda: len(sweeps) >= 2, 5)  # it looked
    assert integrity(db) == []  # and found nothing changed


def test_rename_and_replace_is_caught(tmp_path: Path, root: Path) -> None:
    db = tmp_path / "store.sqlite"
    with running(db, [root], interval=NEVER):
        staged = root / "alpha" / "scripts" / ".run.sh.tmp"
        staged.write_text("echo evil\n", encoding="utf-8")
        staged.rename(root / "alpha" / "scripts" / "run.sh")
        assert wait_for(lambda: ("alpha", "modify", "scripts/run.sh") in integrity(db), 5)
        time.sleep(0.8)  # let any trailing sweep finish
    events = integrity(db)
    # The staged file may or may not be seen before it is renamed away; the replacement is.
    assert ("alpha", "modify", "scripts/run.sh") in events
    assert all(event[0] == "alpha" for event in events)
    with BaselineStore(db) as store:
        assert store.verify_chain().ok


def test_new_skill_directory_is_caught(tmp_path: Path, root: Path) -> None:
    db = tmp_path / "store.sqlite"
    with running(db, [root], interval=NEVER) as sweeps:
        make_skill(root, "gamma")
        assert wait_for(lambda: ("gamma", "create", "scripts/run.sh") in integrity(db), 5)
        assert any(result.new_skills == ("gamma",) for result in sweeps)


def test_missing_root_falls_back_to_the_periodic_sweep(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    root = tmp_path / "not-yet"
    with running(db, [root], interval=0.3) as sweeps:
        make_skill(root, "late")
        assert wait_for(lambda: any(r.new_skills == ("late",) for r in sweeps), 5)
        (root / "late" / "SKILL.md").write_text("---\nname: late\n---\nx\n", encoding="utf-8")
        assert wait_for(lambda: ("late", "modify", "SKILL.md") in integrity(db), 5)


def test_a_failed_sweep_does_not_stop_the_watcher(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "store.sqlite"
    real = watcher_module.sweep_store
    calls = {"n": 0}

    def flaky(*args: object, **kwargs: object) -> SweepResult:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("store busy")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(watcher_module, "sweep_store", flaky)
    with running(db, [root], interval=0.3, use_inotify=False):
        assert wait_for(lambda: calls["n"] >= 3, 5)
        (root / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\nx\n", encoding="utf-8")
        assert wait_for(lambda: bool(integrity(db)), 5)
    assert "sweep failed: RuntimeError: store busy" in capsys.readouterr().err
