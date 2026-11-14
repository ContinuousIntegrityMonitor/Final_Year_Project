"""Skills integrity watcher (T-10): file-system notifications plus a periodic sweep.

Notifications only decide *when* to look. *What* changed is always decided by hashing
(cim.skills.inventory.sweep). So reading a file produces no event, a write that leaves the
content the same produces no event, and nothing is lost when notifications are unavailable:
the periodic sweep finds the change within one interval.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

import watchfiles

from cim.common.store import BaselineStore
from cim.skills.inventory import DEFAULT_ORIGIN, SweepResult, sweep

DEFAULT_INTERVAL_S = 60.0
DEBOUNCE_MS = 400  # group a burst of writes into one sweep
STEP_MS = 50

Report = Callable[[SweepResult], None]


def sweep_store(db: Path, roots: Sequence[Path], origin: str = DEFAULT_ORIGIN) -> SweepResult:
    """One sweep on a store handle that is opened and closed around it.

    The watcher runs for a long time next to other writers; it never keeps a handle open
    between sweeps.
    """
    with BaselineStore(db) as store:
        return sweep(store, roots, origin=origin)


def _log(message: str) -> None:
    print(f"cim skills watch: {message}", file=sys.stderr, flush=True)


def watch(
    db: Path,
    roots: Sequence[Path],
    *,
    origin: str = DEFAULT_ORIGIN,
    interval: float = DEFAULT_INTERVAL_S,
    use_inotify: bool = True,
    stop: threading.Event | None = None,
    report: Report | None = None,
) -> None:
    """Sweep now, then after every notification and at least once per interval, until stopped.

    A sweep that fails is logged and the watcher carries on: one bad sweep must not end
    monitoring.
    """
    stopping = stop or threading.Event()

    def run_sweep() -> None:
        try:
            result = sweep_store(db, roots, origin)
        except Exception as exc:  # noqa: BLE001 - keep watching; the next sweep retries
            _log(f"sweep failed: {type(exc).__name__}: {exc}")
            return
        if report is not None:
            report(result)

    run_sweep()
    watched = [root for root in roots if root.is_dir()] if use_inotify else []
    if not watched:
        # Notifications off, or no root exists yet: the periodic sweep alone.
        while not stopping.wait(interval):
            run_sweep()
        return
    # watch_filter=None: no file is too uninteresting to trigger a look.
    # A root created later is not watched, but every sweep still covers it.
    for _changes in watchfiles.watch(
        *watched,
        watch_filter=None,
        debounce=DEBOUNCE_MS,
        step=STEP_MS,
        stop_event=stopping,
        rust_timeout=max(1, int(interval * 1000)),
        yield_on_timeout=True,
    ):
        run_sweep()
