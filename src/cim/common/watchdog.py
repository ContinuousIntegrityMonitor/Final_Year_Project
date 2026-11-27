"""`cim watch`: the supervisor for CIM's long-running collectors (T-13, design note section 6).

- **Children** come from the config: the skills watcher (`python -m cim.skills watch`) when
  skill roots are set, and the HTTP gateway (`python -m cim http-gateway`) when
  `[mcp.gateway]` exists. The wrappers (`cim proxy`, `cim skills exec`) are not children: they
  belong to an agent's session, so they are only listed, from their session files.
- **Liveness:** a child is down when its process exits, and hung when its heartbeat has not
  moved for three `heartbeat_s` (a hung child is killed, then treated as down).
- **Restart:** after 1, 2, 4 ... seconds, up to `backoff_max_s`; the backoff resets once a
  child has stayed up for `backoff_max_s`. After `max_restarts` restarts within 10 minutes,
  the supervisor gives up on that child and keeps the others running.
- **Evidence:** each restart is a `collector_restarted` alert and each give-up a
  `collector_failed` alert, under a `monitor` artefact named after the child (contract 1.1,
  `MonitorAlertPayload`). Heartbeats and `watch.json` are runtime state, outside the chain.
- **Stop:** SIGTERM to every child (`terminate()`, which also works on Windows), 5 s, SIGKILL.

The loop is driven by `poll(now)`, so tests can run it against fake processes and a fake clock.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from cim.common.config import CimConfig
from cim.common.runtime import (
    clear_heartbeat,
    heartbeat_age,
    utc_now,
    write_watch_state,
)
from cim.common.schema.alerts import MonitorAlertPayload
from cim.common.schema.envelope import Artefact, Event
from cim.common.store import BaselineStore

RESTART_WINDOW_S = 600.0  # max_restarts counts restarts inside this window
HUNG_AFTER_BEATS = 3
STOP_GRACE_S = 5.0
POLL_S = 0.5
SKILLS_WATCHER = "skills-watcher"
HTTP_GATEWAY = "http-gateway"

Reason = Literal["exited", "hung"]


class Process(Protocol):
    """The part of `subprocess.Popen` the supervisor uses."""

    pid: int

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


Launcher = Callable[[Sequence[str]], Process]


@dataclass(frozen=True)
class ChildSpec:
    name: str  # the monitor component, e.g. "skills-watcher"
    argv: tuple[str, ...]
    heartbeat: bool = True  # False: liveness is the process alone


@dataclass
class _Child:
    spec: ChildSpec
    process: Process | None = None
    started_at: float = 0.0  # monotonic
    down_since: float | None = None
    reason: Reason = "exited"
    exit_code: int | None = None
    next_start: float | None = None
    backoff: float = 1.0
    restarts: deque[float] = field(default_factory=deque)  # monotonic times, inside the window
    total_restarts: int = 0
    failed: bool = False

    def state(self) -> str:
        if self.failed:
            return "failed"
        return "running" if self.down_since is None else "restarting"


def children_for(config: CimConfig, *, store: Path) -> list[ChildSpec]:
    """What `cim watch` supervises for this config."""
    python = sys.executable
    found: list[ChildSpec] = []
    if config.skills.roots:
        argv = [python, "-m", "cim.skills", "watch", "--db", str(store)]
        for root in config.skills.roots:
            argv += ["--root", str(root)]
        argv += [
            "--origin",
            config.store.origin,
            "--interval",
            str(config.skills.sweep_interval_s),
            "--heartbeat-s",
            str(config.watchdog.heartbeat_s),
        ]
        if not config.skills.inotify:
            argv.append("--no-inotify")
        found.append(ChildSpec(SKILLS_WATCHER, tuple(argv)))
    if config.mcp.gateway is not None and config.source is not None:
        argv = [python, "-m", "cim", "http-gateway", "--config", str(config.source)]
        argv += ["--db", str(store)]
        found.append(ChildSpec(HTTP_GATEWAY, tuple(argv)))
    return found


def record_monitor_alert(store: Path, origin: str, payload: MonitorAlertPayload, ts: str) -> int:
    """Append one watchdog alert under the child's `monitor` artefact."""
    body = payload.model_dump(mode="json")
    Event(
        ts=ts,
        artefact=Artefact(type="monitor", component=payload.component),
        kind="alert",
        payload=body,
    )  # the contract check every writer goes through
    store.parent.mkdir(parents=True, exist_ok=True)
    with BaselineStore(store) as handle:
        artefact = handle.get_or_create_artefact("monitor", payload.component, origin)
        return handle.append_record(artefact, "alert", body, ts)


def _launch(argv: Sequence[str]) -> Process:
    return subprocess.Popen(list(argv), stdin=subprocess.DEVNULL)  # noqa: S603 - our own argv


class Supervisor:
    def __init__(
        self,
        store: Path,
        children: Sequence[ChildSpec],
        *,
        origin: str,
        heartbeat_s: int,
        backoff_max_s: int,
        max_restarts: int,
        launch: Launcher = _launch,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.store = store
        self.origin = origin
        self.heartbeat_s = heartbeat_s
        self.backoff_max_s = backoff_max_s
        self.max_restarts = max_restarts
        self._launch = launch
        self._clock = clock
        self._wall = wall
        self._log = log or (lambda message: print(f"cim watch: {message}", file=sys.stderr))
        self._children = [_Child(spec) for spec in children]
        self._started = utc_now()
        self._last_written = -1.0

    @property
    def children(self) -> tuple[_Child, ...]:
        return tuple(self._children)

    def start(self) -> None:
        now = self._clock()
        for child in self._children:
            self._spawn(child, now)
            self._log(f"started {child.spec.name} (pid {self._pid(child)})")
        self.write_state(force=True)

    def poll(self) -> None:
        """One supervision step: notice exits and hangs, restart what is due."""
        now = self._clock()
        for child in self._children:
            if child.failed:
                continue
            if child.down_since is None:
                self._check(child, now)
            if child.down_since is not None and child.next_start is not None:
                if now >= child.next_start:
                    self._restart(child, now)
        self.write_state()

    def run(self, stop: threading.Event) -> None:
        self.start()
        try:
            while not stop.wait(POLL_S):
                self.poll()
        finally:
            self.stop()

    def stop(self) -> None:
        running = [c for c in self._children if c.process is not None and c.process.poll() is None]
        for child in running:
            assert child.process is not None
            child.process.terminate()
        deadline = self._clock() + STOP_GRACE_S
        for child in running:
            assert child.process is not None
            try:
                child.process.wait(timeout=max(0.0, deadline - self._clock()))
            except subprocess.TimeoutExpired:
                child.process.kill()
                child.process.wait()
        self.write_state(force=True, stopped=True)

    def write_state(self, *, force: bool = False, stopped: bool = False) -> None:
        """`watch.json`, at most once per second unless forced. Runtime state, not evidence."""
        now = self._clock()
        if not force and now - self._last_written < 1.0:
            return
        self._last_written = now
        write_watch_state(
            self.store,
            {
                "pid": os.getpid() if not stopped else 0,
                "started": self._started,
                "updated": utc_now(),
                "heartbeat_s": self.heartbeat_s,
                "children": [
                    {
                        "name": c.spec.name,
                        "pid": self._pid(c),
                        "state": "stopped" if stopped else c.state(),
                        "restarts": c.total_restarts,
                        "last_exit": c.exit_code,
                    }
                    for c in self._children
                ],
            },
        )

    def _check(self, child: _Child, now: float) -> None:
        assert child.process is not None
        code = child.process.poll()
        if code is not None:
            self._down(child, now, "exited", code)
            return
        if not child.spec.heartbeat:
            return
        limit = HUNG_AFTER_BEATS * self.heartbeat_s
        if now - child.started_at < limit:
            return  # still starting: give it three beats before judging
        age = heartbeat_age(self.store, child.spec.name, self._wall())
        if age is None or age > limit:
            seen = "missing" if age is None else f"{age:.1f}s old"
            self._log(f"{child.spec.name} is hung (heartbeat {seen}); killing it")
            child.process.kill()
            try:
                child.process.wait(timeout=STOP_GRACE_S)
            except subprocess.TimeoutExpired:
                pass
            self._down(child, now, "hung", None)

    def _down(self, child: _Child, now: float, reason: Reason, code: int | None) -> None:
        if now - child.started_at >= self.backoff_max_s:
            child.backoff = 1.0  # it had stayed up: start the backoff again
        child.down_since = now
        child.reason = reason
        child.exit_code = code
        child.next_start = now + child.backoff
        self._log(f"{child.spec.name} {reason} (code {code}); restart in {child.backoff:g}s")
        child.backoff = min(child.backoff * 2, float(self.backoff_max_s))

    def _restart(self, child: _Child, now: float) -> None:
        assert child.down_since is not None
        while child.restarts and now - child.restarts[0] > RESTART_WINDOW_S:
            child.restarts.popleft()
        gap = round(now - child.down_since)
        if len(child.restarts) >= self.max_restarts:
            child.failed = True
            child.next_start = None
            self._log(f"giving up on {child.spec.name} after {len(child.restarts)} restarts")
            self._record(child, "collector_failed", "gave_up", gap)
            return
        self._spawn(child, now)
        child.restarts.append(now)
        child.total_restarts += 1
        self._log(f"restarted {child.spec.name} (pid {self._pid(child)}) after {gap}s")
        self._record(child, "collector_restarted", child.reason, gap)

    def _spawn(self, child: _Child, now: float) -> None:
        clear_heartbeat(self.store, child.spec.name)  # an old heartbeat must not vouch for it
        child.process = self._launch(child.spec.argv)
        child.started_at = now
        child.down_since = None
        child.next_start = None

    def _record(
        self,
        child: _Child,
        code: Literal["collector_restarted", "collector_failed"],
        reason: Literal["exited", "hung", "gave_up"],
        gap: int,
    ) -> None:
        payload = MonitorAlertPayload(
            code=code,
            reason=reason,
            component=child.spec.name,
            exit_code=child.exit_code,
            gap_s=max(0, gap),
            restarts=child.total_restarts,
        )
        try:
            record_monitor_alert(self.store, self.origin, payload, utc_now())
        except Exception as exc:  # noqa: BLE001 - supervising matters more than this one record
            self._log(f"could not record {code} for {child.spec.name}: {exc}")

    @staticmethod
    def _pid(child: _Child) -> int | None:
        return child.process.pid if child.process is not None else None
