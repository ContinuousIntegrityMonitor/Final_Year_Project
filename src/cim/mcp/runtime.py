"""Runtime state next to the store (T-13 design §6; Hamza decision 7).

Heartbeats and session files are not evidence — they stay out of the hash chain.
Layout (relative to the store path ``S``):

- ``S.run/<name>.heartbeat`` — daemon liveness (gateway); touched every ``heartbeat_s``
- ``S.run/sessions/<name>-<pid>.json`` — wrapper registration (proxy); removed on exit

``cim watch`` (Fasih stage 4) will supervise heartbeats and list sessions; this module
only writes the files so that work can land before the supervisor exists.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def run_dir(store: Path) -> Path:
    """``<store>.run`` beside the SQLite file (e.g. ``logs/cim-store.sqlite.run``)."""
    return Path(f"{store}.run")


def sessions_dir(store: Path) -> Path:
    return run_dir(store) / "sessions"


def heartbeat_path(store: Path, name: str) -> Path:
    return run_dir(store) / f"{name}.heartbeat"


def session_path(store: Path, name: str, pid: int | None = None) -> Path:
    return sessions_dir(store) / f"{name}-{pid if pid is not None else os.getpid()}.json"


def touch_heartbeat(store: Path, name: str) -> Path:
    """Create or refresh a daemon heartbeat file. Returns its path."""
    path = heartbeat_path(store, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") + "\n", encoding="utf-8")
    return path


def clear_heartbeat(store: Path, name: str) -> None:
    path = heartbeat_path(store, name)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


@dataclass(frozen=True)
class SessionInfo:
    name: str
    pid: int
    server_id: str
    started: str
    command: tuple[str, ...] = ()


def write_session(store: Path, info: SessionInfo) -> Path:
    path = session_path(store, info.name, info.pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = asdict(info)
    payload["command"] = list(info.command)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def clear_session(store: Path, name: str, pid: int | None = None) -> None:
    path = session_path(store, name, pid)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


@contextmanager
def proxy_session(
    store: Path,
    *,
    server_id: str,
    command: list[str],
    name: str = "proxy",
) -> Iterator[Path]:
    """Register a proxy session for the life of the ``with`` block."""
    info = SessionInfo(
        name=name,
        pid=os.getpid(),
        server_id=server_id,
        started=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        command=tuple(command),
    )
    path = write_session(store, info)
    try:
        yield path
    finally:
        clear_session(store, name, info.pid)


class HeartbeatThread(threading.Thread):
    """Touches ``<store>.run/<name>.heartbeat`` until stopped."""

    def __init__(self, store: Path, name: str, interval_s: float = 10.0) -> None:
        super().__init__(name=f"cim-heartbeat-{name}", daemon=True)
        self._store = store
        self._daemon_name = name
        self._interval = max(0.5, float(interval_s))
        self._halt = threading.Event()  # not `_stop`: Thread already uses that name

    def stop(self) -> None:
        self._halt.set()

    def run(self) -> None:
        touch_heartbeat(self._store, self._daemon_name)
        while not self._halt.wait(self._interval):
            touch_heartbeat(self._store, self._daemon_name)
        clear_heartbeat(self._store, self._daemon_name)


def sleep_briefly() -> None:
    """Tiny pause so tests can observe a heartbeat write without racing."""
    time.sleep(0.01)
