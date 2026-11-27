"""`cim watch` supervisor (T-13, design note section 6), with fake processes and a fake clock."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cim.cli import app
from cim.common import watchdog
from cim.common.config import parse_config
from cim.common.runtime import (
    heartbeat_path,
    read_sessions,
    read_watch_state,
    session,
    sessions_dir,
    touch_heartbeat,
    write_watch_state,
)
from cim.common.status import load_status
from cim.common.store import BaselineStore
from cim.common.watchdog import ChildSpec, Supervisor
from cim.skills.watcher import watch

runner = CliRunner()


class FakeProcess:
    count = 0

    def __init__(self, argv: Sequence[str]) -> None:
        FakeProcess.count += 1
        self.pid = 50_000 + FakeProcess.count
        self.argv = tuple(argv)
        self.code: int | None = None
        self.stubborn = False  # ignores terminate()
        self.signals: list[str] = []

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.signals.append("TERM")
        if not self.stubborn:
            self.code = -15

    def kill(self) -> None:
        self.signals.append("KILL")
        self.code = -9

    def wait(self, timeout: float | None = None) -> int:
        if self.code is None:
            raise subprocess.TimeoutExpired("fake", timeout or 0)
        return self.code


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _supervisor(
    tmp_path: Path, *specs: ChildSpec, max_restarts: int = 5, heartbeat_s: int = 10
) -> tuple[Supervisor, Clock, list[FakeProcess]]:
    clock = Clock()
    launched: list[FakeProcess] = []

    def launch(argv: Sequence[str]) -> FakeProcess:
        process = FakeProcess(argv)
        launched.append(process)
        return process

    supervisor = Supervisor(
        tmp_path / "store.sqlite",
        specs or (ChildSpec("skills-watcher", ("watcher",), heartbeat=False),),
        origin="test",
        heartbeat_s=heartbeat_s,
        backoff_max_s=8,
        max_restarts=max_restarts,
        launch=launch,
        clock=clock,
        wall=time.time,
        log=lambda _message: None,
    )
    return supervisor, clock, launched


def _alerts(store: Path) -> list[dict[str, Any]]:
    if not store.exists():
        return []
    with BaselineStore(store) as handle:
        assert handle.verify_chain().ok
        types = {a.id: (a.type, a.name) for a in handle.read_artefacts()}
        return [
            {**json.loads(r.payload), "artefact": types[r.artefact_id]}
            for r in handle.read_records()
            if r.kind == "alert"
        ]


def test_a_child_that_exits_is_restarted_with_backoff(tmp_path: Path) -> None:
    supervisor, clock, launched = _supervisor(tmp_path)
    supervisor.start()
    starts = []
    for _round in range(4):
        launched[-1].code = 1
        supervisor.poll()  # notices the exit
        down = clock.now
        while len(launched) == len(starts) + 1:
            clock.now += 0.5
            supervisor.poll()
        starts.append(clock.now - down)
    assert starts == [1.0, 2.0, 4.0, 8.0]  # 1, 2, 4 ... capped at backoff_max_s
    alerts = _alerts(tmp_path / "store.sqlite")
    assert [a["code"] for a in alerts] == ["collector_restarted"] * 4
    assert alerts[0] == {
        "code": "collector_restarted",
        "reason": "exited",
        "component": "skills-watcher",
        "exit_code": 1,
        "gap_s": 1,
        "restarts": 1,
        "artefact": ("monitor", "skills-watcher"),
    }


def test_backoff_resets_after_a_stable_run(tmp_path: Path) -> None:
    supervisor, clock, launched = _supervisor(tmp_path)
    supervisor.start()
    launched[-1].code = 1
    supervisor.poll()
    clock.now += 1
    supervisor.poll()  # restarted; next backoff would be 2
    clock.now += 8  # up for backoff_max_s
    supervisor.poll()
    launched[-1].code = 1
    supervisor.poll()
    clock.now += 1
    supervisor.poll()
    assert len(launched) == 3  # restarted after 1 s again, not 2


def test_it_gives_up_after_max_restarts_and_keeps_the_others(tmp_path: Path) -> None:
    flaky = ChildSpec("skills-watcher", ("watcher",), heartbeat=False)
    steady = ChildSpec("http-gateway", ("gateway",), heartbeat=False)
    supervisor, clock, launched = _supervisor(tmp_path, flaky, steady, max_restarts=2)
    supervisor.start()
    gateway = launched[1]
    for _round in range(3):
        next(p for p in reversed(launched) if p.argv == ("watcher",)).code = 1
        supervisor.poll()
        clock.now += 10
        supervisor.poll()
    codes = [(a["code"], a["reason"]) for a in _alerts(tmp_path / "store.sqlite")]
    assert codes == [
        ("collector_restarted", "exited"),
        ("collector_restarted", "exited"),
        ("collector_failed", "gave_up"),
    ]
    assert [c.state() for c in supervisor.children] == ["failed", "running"]
    assert gateway.code is None and sum(p.argv == ("gateway",) for p in launched) == 1


def test_restarts_older_than_ten_minutes_do_not_count(tmp_path: Path) -> None:
    supervisor, clock, launched = _supervisor(tmp_path, max_restarts=1)
    supervisor.start()
    launched[-1].code = 1
    supervisor.poll()
    clock.now += 1
    supervisor.poll()  # restart 1
    clock.now += 700
    launched[-1].code = 1
    supervisor.poll()
    clock.now += 1
    supervisor.poll()
    assert len(launched) == 3 and not supervisor.children[0].failed


def test_a_child_whose_heartbeat_stops_is_killed_and_restarted(tmp_path: Path) -> None:
    store = tmp_path / "store.sqlite"
    spec = ChildSpec("skills-watcher", ("watcher",))
    supervisor, clock, launched = _supervisor(tmp_path, spec, heartbeat_s=1)
    supervisor.start()
    clock.now += 2
    supervisor.poll()  # inside the three-beat grace: no heartbeat yet is fine
    assert launched[0].code is None
    touch_heartbeat(store, "skills-watcher")
    clock.now += 2
    supervisor.poll()  # fresh heartbeat
    assert launched[0].code is None
    old = time.time() - 10
    os.utime(heartbeat_path(store, "skills-watcher"), (old, old))
    supervisor.poll()
    assert launched[0].signals == ["KILL"]
    clock.now += 1
    supervisor.poll()
    assert len(launched) == 2
    assert not heartbeat_path(store, "skills-watcher").exists()  # cleared for the new child
    assert [(a["code"], a["reason"]) for a in _alerts(store)] == [("collector_restarted", "hung")]


def test_stop_terminates_then_kills(tmp_path: Path) -> None:
    gentle = ChildSpec("a", ("a",), heartbeat=False)
    stubborn = ChildSpec("b", ("b",), heartbeat=False)
    supervisor, _clock, launched = _supervisor(tmp_path, gentle, stubborn)
    supervisor.start()
    launched[1].stubborn = True
    supervisor.stop()
    assert launched[0].signals == ["TERM"]
    assert launched[1].signals == ["TERM", "KILL"]
    state = read_watch_state(tmp_path / "store.sqlite")
    assert state is not None and not state.running  # pid 0: stopped
    assert [c["state"] for c in state.children] == ["stopped", "stopped"]


def test_the_state_file_says_what_runs(tmp_path: Path) -> None:
    supervisor, _clock, launched = _supervisor(tmp_path)
    supervisor.start()
    state = read_watch_state(tmp_path / "store.sqlite")
    assert state is not None and state.running and state.pid == os.getpid()
    assert state.children == (
        {
            "name": "skills-watcher",
            "pid": launched[0].pid,
            "state": "running",
            "restarts": 0,
            "last_exit": None,
        },
    )


def test_children_follow_the_config(tmp_path: Path) -> None:
    store = tmp_path / "s.sqlite"
    none = parse_config({})
    assert watchdog.children_for(none, store=store) == []
    source = tmp_path / "cim.toml"
    config = parse_config(
        {
            "skills": {"roots": ["skills"], "sweep_interval_s": 5, "inotify": False},
            "store": {"origin": "laptop"},
            "watchdog": {"heartbeat_s": 3},
            "mcp": {"gateway": {"routes": [{"id": "demo", "upstream": "http://x/"}]}},
        },
        source=source,
    )
    skills, gateway = watchdog.children_for(config, store=store)
    assert skills.name == "skills-watcher" and gateway.name == "http-gateway"
    assert skills.argv[:4] == (sys.executable, "-m", "cim.skills", "watch")
    assert "--no-inotify" in skills.argv
    assert skills.argv[skills.argv.index("--root") + 1] == str(tmp_path / "skills")
    assert skills.argv[skills.argv.index("--heartbeat-s") + 1] == "3"
    assert skills.argv[skills.argv.index("--origin") + 1] == "laptop"
    assert gateway.argv[gateway.argv.index("--config") + 1] == str(source)


def test_the_skills_watcher_beats_from_its_own_loop(tmp_path: Path) -> None:
    beats: list[float] = []
    sweeps: list[object] = []
    stop = threading.Event()
    thread = threading.Thread(
        target=watch,
        args=(tmp_path / "s.sqlite", [tmp_path]),
        kwargs={
            "interval": 0.6,
            "use_inotify": False,
            "stop": stop,
            "report": sweeps.append,
            "heartbeat": lambda: beats.append(time.monotonic()),
            "heartbeat_s": 0.1,
        },
    )
    thread.start()
    time.sleep(0.9)
    stop.set()
    thread.join(timeout=5)
    assert len(beats) >= 6  # every 0.1 s
    assert 2 <= len(sweeps) <= 3  # once at start, then every 0.6 s: beats do not sweep


def test_sessions_live_and_left_behind(tmp_path: Path) -> None:
    store = tmp_path / "s.sqlite"
    with session(store, "exec", skill_id="word-count") as path:
        live = read_sessions(store)
        assert [(s.name, s.subject, s.running) for s in live] == [("exec", "word-count", True)]
    assert not path.exists()
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    sessions_dir(store).mkdir(parents=True, exist_ok=True)
    (sessions_dir(store) / f"proxy-{gone.pid}.json").write_text(
        json.dumps({"name": "proxy", "pid": gone.pid, "server_id": "hexstrike", "started": "x"}),
        encoding="utf-8",
    )
    assert [(s.name, s.subject, s.running) for s in read_sessions(store)] == [
        ("proxy", "hexstrike", False)
    ]


def _store(tmp_path: Path) -> Path:
    db = tmp_path / "s.sqlite"
    with BaselineStore(db) as handle:
        handle.append_artefact("skill", "word-count", "test")
    return db


def test_status_exit_2_when_the_monitor_stopped(tmp_path: Path) -> None:
    db = _store(tmp_path)
    assert load_status(db).exit_code() == 0  # never watched: as before
    assert load_status(db).exit_code(require_watch=True) == 2
    write_watch_state(db, {"pid": os.getpid(), "started": "t", "updated": "t", "children": []})
    running = load_status(db)
    assert running.monitor_running and running.exit_code(require_watch=True) == 0
    write_watch_state(db, {"pid": 0, "started": "t", "updated": "u", "children": []})
    stopped = runner.invoke(app, ["status", "--db", str(db)])
    assert stopped.exit_code == 2
    assert "cim watch NOT RUNNING (last update u)" in stopped.output


def test_status_lists_children_and_sessions(tmp_path: Path) -> None:
    db = _store(tmp_path)
    write_watch_state(
        db,
        {
            "pid": os.getpid(),
            "started": "2026-11-27T10:00:00Z",
            "updated": "now",
            "children": [{"name": "skills-watcher", "state": "running", "restarts": 1}],
        },
    )
    with session(db, "exec", skill_id="word-count"):
        result = runner.invoke(app, ["status", "--db", str(db), "--require-watch"])
        shown = json.loads(runner.invoke(app, ["status", "--db", str(db), "--json"]).output)
    assert result.exit_code == 0, result.output
    assert "skills-watcher running (1 restart)" in result.output
    assert "sessions: exec word-count (pid " in result.output
    assert shown["collectors"]["supervised"] is True
    assert [s["name"] for s in shown["collectors"]["sessions"]] == ["exec"]


def test_cim_watch_refuses_nothing_and_a_second_copy(tmp_path: Path) -> None:
    empty = tmp_path / "empty.toml"
    empty.write_text("", encoding="utf-8")
    nothing = runner.invoke(app, ["watch", "--config", str(empty)])
    assert nothing.exit_code == 2 and "nothing to supervise" in nothing.output
    config = tmp_path / "cim.toml"
    config.write_text('[store]\npath = "s.sqlite"\n[skills]\nroots = ["."]\n', encoding="utf-8")
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        write_watch_state(tmp_path / "s.sqlite", {"pid": other.pid, "started": "t", "updated": "t"})
        twice = runner.invoke(app, ["watch", "--config", str(config)])
    finally:
        other.kill()
        other.wait()
    assert twice.exit_code == 1 and "already running" in twice.output


@pytest.mark.skipif(sys.platform == "win32", reason="the unit is for VM-MON (Linux)")
def test_init_prints_a_systemd_unit(tmp_path: Path) -> None:
    target = tmp_path / "cim.toml"
    result = runner.invoke(app, ["init", str(target), "--systemd"])
    assert result.exit_code == 0 and target.exists()
    assert result.stdout.startswith("# ~/.config/systemd/user/cim-watch.service")  # unit only
    assert f"ExecStart={sys.executable} -m cim watch --config {target.resolve()}" in result.output
    assert "Restart=on-failure" in result.output
    again = runner.invoke(app, ["init", str(target), "--systemd"])
    assert again.exit_code == 0 and "init: wrote" not in again.output  # existing file kept


def test_skills_exec_registers_a_session_while_it_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    from cim.skills import execute

    db = tmp_path / "s.sqlite"
    seen: list[Any] = []

    def run_helper(_request: Any, _out: Any, _err: Any) -> int:
        seen.extend(read_sessions(db))
        return 0

    monkeypatch.setattr(execute, "_run", run_helper)
    request = execute.Request(
        db=db,
        roots=(),
        skill_id="word-count",
        script="scripts/count.py",
        args=(),
        timeout=1.0,
        origin="test",
        verbose=False,
    )
    assert execute.run(request, io.BytesIO(), io.BytesIO()) == 0
    assert [(s.name, s.subject, s.running) for s in seen] == [("exec", "word-count", True)]
    assert read_sessions(db) == []  # removed when the run ends
