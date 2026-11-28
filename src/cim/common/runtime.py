"""Runtime state beside the store, for both sides (T-13 design note, section 6; border).

Heartbeats, session files and the supervisor's state file are not evidence: they stay out of
the hash chain. They live in `<store>.run/`:

- `<name>.heartbeat`: a daemon's liveness, touched every `heartbeat_s`;
- `sessions/<name>-<pid>.json`: a wrapper (`cim proxy`, `cim skills exec`) while it runs;
- `watch.json`: what `cim watch` supervises, rewritten while it runs.

The file layout and the heartbeat / proxy-session writers are Hamza's (`cim.mcp.runtime`,
T-13 decision 7); they are re-exported here so the skills side and the shared commands do not
import from the MCP side.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cim.mcp.runtime import (
    clear_heartbeat,
    heartbeat_path,
    run_dir,
    sessions_dir,
    touch_heartbeat,
)

__all__ = [
    "Session",
    "WatchState",
    "alive",
    "clear_heartbeat",
    "heartbeat_age",
    "heartbeat_path",
    "read_sessions",
    "read_watch_state",
    "run_dir",
    "session",
    "sessions_dir",
    "touch_heartbeat",
    "watch_state_path",
    "write_watch_state",
]


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def alive(pid: int) -> bool:
    """True while a process with this id exists. Never sends it a signal."""
    if pid <= 0:
        return False
    if sys.platform == "win32":  # os.kill(pid, 0) would send CTRL_C_EVENT there
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # it exists, under another user
    return True


def heartbeat_age(store: Path, name: str, now: float) -> float | None:
    """Seconds since the daemon last touched its heartbeat (wall clock), or None if it never did."""
    try:
        return max(0.0, now - heartbeat_path(store, name).stat().st_mtime)
    except FileNotFoundError:
        return None


@dataclass(frozen=True)
class Session:
    """One wrapper's session file."""

    name: str  # "proxy", "exec"
    pid: int
    started: str
    subject: str  # the server or skill it runs
    path: Path
    running: bool  # False: the process is gone but its file stayed ("ended without closing")


def read_sessions(store: Path) -> list[Session]:
    """Every session file beside the store, oldest first. Unreadable files are skipped."""
    folder = sessions_dir(store)
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pid = int(data["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        subject = data.get("skill_id") or data.get("server_id") or ""
        found.append(
            Session(
                name=str(data.get("name", path.stem.rsplit("-", 1)[0])),
                pid=pid,
                started=str(data.get("started", "")),
                subject=str(subject),
                path=path,
                running=alive(pid),
            )
        )
    return sorted(found, key=lambda item: (item.started, item.path.name))


@contextmanager
def session(store: Path, name: str, **fields: Any) -> Iterator[Path]:
    """Register this process as a wrapper session for the `with` block (skills `exec`)."""
    pid = os.getpid()
    path = sessions_dir(store) / f"{name}-{pid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"name": name, "pid": pid, "started": utc_now(), **fields}
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    try:
        yield path
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def watch_state_path(store: Path) -> Path:
    return run_dir(store) / "watch.json"


@dataclass(frozen=True)
class WatchState:
    """What `cim watch` last wrote about itself and its children."""

    pid: int
    started: str
    updated: str
    heartbeat_s: int
    children: tuple[dict[str, Any], ...]
    running: bool  # its process still exists


def write_watch_state(store: Path, body: dict[str, Any]) -> None:
    """Replace `watch.json` in one step, so a reader never sees half a file."""
    path = watch_state_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    partial.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    partial.replace(path)


def read_watch_state(store: Path) -> WatchState | None:
    """The supervisor's last state, or None if `cim watch` never ran for this store."""
    try:
        data = json.loads(watch_state_path(store).read_text(encoding="utf-8"))
        pid = int(data["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    children = data.get("children")
    return WatchState(
        pid=pid,
        started=str(data.get("started", "")),
        updated=str(data.get("updated", "")),
        heartbeat_s=int(data.get("heartbeat_s", 10)),
        children=tuple(item for item in children if isinstance(item, dict))
        if isinstance(children, list)
        else (),
        running=alive(pid),
    )
