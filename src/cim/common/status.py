"""What `cim status` and `cim events` show (T-13, design note section 7; border file).

The store is read once. Each side's own read model does the work: `cim.skills.board` for
skills and `cim.mcp.summary` for MCP. This module only adds them up and words the result.

- **Findings** count changed artefacts, not records (decision 6): one rug pull can write a
  drift record per changed field, and one skill edit a record per file. Each changed artefact
  is listed with all its changes.
- **Behaviour alerts** are the T-16 drift codes. **Monitor events** are the watchdog's
  (`collector_restarted`, `collector_failed`). **Capture faults** are records saying that
  something could not be recorded or scored (`proxy_*`, `skill_score_failed`).
- **Collectors** come from the runtime files beside the store (`cim.common.runtime`): what
  `cim watch` last wrote about itself and its children, and the wrappers' session files.
- **Exit status** (decision 6): 0 clean; 1 when the chain is broken or there is any finding,
  behaviour alert, monitor event or capture fault; 2 when the monitor is not running, which
  wins over 1. "Not running" means `cim watch` once ran for this store and runs no longer, or,
  when the caller requires a monitor, that it never ran.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from cim.common.runtime import Session, WatchState, read_sessions, read_watch_state
from cim.common.store import BaselineStore, StoredArtefact, StoredRecord
from cim.mcp.summary import McpSummary, summarise
from cim.mcp.summary import event_label as mcp_label
from cim.skills.board import SkillsBoard, rail_label, skills_board
from cim.skills.envelope import WARMUP

Side = Literal["skills", "mcp", "monitor", "other"]
MONITOR_CODES = frozenset({"collector_restarted", "collector_failed"})
SKILL_BEHAVIOUR_CODE = "skill_behaviour_drift"
CAPTURE_CODES = frozenset({"proxy_malformed_frame", "proxy_capture_failed", "skill_score_failed"})
_SIDES: dict[str, Side] = {
    "skill": "skills",
    "mcp_server": "mcp",
    "mcp_tool": "mcp",
    "monitor": "monitor",
}


@dataclass(frozen=True)
class Finding:
    """One changed artefact and every change recorded against it, oldest first."""

    side: Literal["skills", "mcp"]
    artefact: str  # "skill word-count", "mcp hexstrike/nmap_scan", "mcp hexstrike"
    changes: tuple[str, ...]
    last_ts: str


@dataclass(frozen=True)
class Status:
    store: Path
    chain_ok: bool
    records: int
    tip: str | None
    hash_version: int
    broken_at: int | None
    chain_reason: str
    skills: SkillsBoard
    mcp: McpSummary
    findings: tuple[Finding, ...]
    skill_alerts: int
    monitor_events: int
    capture_faults: int
    watch: WatchState | None = None  # None: `cim watch` never ran for this store
    sessions: tuple[Session, ...] = ()

    @property
    def behaviour_alerts(self) -> int:
        return self.skill_alerts + self.mcp.behaviour_alerts

    @property
    def skills_learning(self) -> int:
        return sum(1 for row in self.skills.skills if row.runs < WARMUP)

    @property
    def monitor_running(self) -> bool:
        return self.watch is not None and self.watch.running

    def exit_code(self, *, require_watch: bool = False) -> int:
        """0 clean, 1 something found, 2 monitor not running (wins over 1)."""
        if (self.watch is not None or require_watch) and not self.monitor_running:
            return 2
        return 0 if self.clean else 1

    @property
    def clean(self) -> bool:
        return self.chain_ok and not (
            self.findings or self.behaviour_alerts or self.monitor_events or self.capture_faults
        )


def load_status(db: Path) -> Status:
    """Verify the chain and read the store once."""
    with BaselineStore(db) as store:
        chain = store.verify_chain()
        records = store.read_records()
    skills = skills_board(records)
    mcp = summarise(records)
    findings = _skill_findings(skills, records) + _mcp_findings(mcp)
    codes = [_code(record) for record in records if record.kind == "alert"]
    return Status(
        store=db,
        chain_ok=chain.ok,
        records=chain.count,
        tip=chain.tip,
        hash_version=chain.hash_version,
        broken_at=chain.broken_at,
        chain_reason=chain.reason,
        skills=skills,
        mcp=mcp,
        findings=tuple(sorted(findings, key=lambda f: (f.last_ts, f.artefact))),
        skill_alerts=sum(code == SKILL_BEHAVIOUR_CODE for code in codes),
        monitor_events=sum(code in MONITOR_CODES for code in codes),
        capture_faults=sum(code in CAPTURE_CODES for code in codes),
        watch=read_watch_state(db),
        sessions=tuple(read_sessions(db)),
    )


def render(status: Status) -> list[str]:
    """The lines `cim status` prints."""
    tip = f"{status.tip[:4]}…{status.tip[-2:]}" if status.tip else "-"
    chain = "chain ok" if status.chain_ok else f"CHAIN BROKEN at record {status.broken_at}"
    mcp = status.mcp
    servers = len(mcp.tools)
    lines = [
        f"store      {status.store}   {chain}   {status.records} records   tip {tip}   "
        f"hash v{status.hash_version}",
        *_collector_lines(status),
        f"inventory  mcp: {servers} server{'s' * (servers != 1)}, {mcp.tool_count} tools   "
        f"skills: {len(status.skills.skills)}",
    ]
    count = len(status.findings)
    lines.append(
        f"findings   {count} changed artefact{'s' * (count != 1)}" + (":" if count else "")
    )
    for finding in status.findings:
        clock = finding.last_ts[11:19] if len(finding.last_ts) >= 19 else finding.last_ts
        lines.append(f"           {finding.artefact} ({'; '.join(finding.changes)}, {clock})")
    lines.append(
        f"           {_count(status.behaviour_alerts, 'behaviour alert')}   "
        f"{_count(status.monitor_events, 'monitor event')}   "
        f"{_count(status.capture_faults, 'capture fault')}"
    )
    lines.append(
        f"learning   mcp: {mcp.learning_tools()} tool{'s' * (mcp.learning_tools() != 1)} "
        f"under {WARMUP} calls   "
        f"skills: {status.skills_learning} under {WARMUP} runs"
    )
    if not status.chain_ok:
        lines.append(f"chain      {status.chain_reason}")
    return lines


def as_dict(status: Status) -> dict[str, Any]:
    """`cim status --json`."""
    return {
        "store": str(status.store),
        "chain": {
            "ok": status.chain_ok,
            "records": status.records,
            "tip": status.tip,
            "hash_version": status.hash_version,
            "broken_at": status.broken_at,
            "reason": status.chain_reason or None,
        },
        "collectors": _collectors(status),
        "inventory": {
            "mcp": {"servers": len(status.mcp.tools), "tools": status.mcp.tool_count},
            "skills": len(status.skills.skills),
        },
        "findings": [
            {
                "side": f.side,
                "artefact": f.artefact,
                "changes": list(f.changes),
                "last_ts": f.last_ts,
            }
            for f in status.findings
        ],
        "behaviour_alerts": {
            "skills": status.skill_alerts,
            "mcp": status.mcp.behaviour_alerts,
        },
        "monitor_events": status.monitor_events,
        "capture_faults": status.capture_faults,
        "learning": {
            "mcp_tools": status.mcp.learning_tools(),
            "skills": status.skills_learning,
            "warmup": WARMUP,
        },
        "clean": status.clean,
    }


@dataclass(frozen=True)
class Event:
    record_id: int
    ts: str
    side: Side
    kind: str
    label: str

    def render(self) -> str:
        return f"#{self.record_id} {self.ts} {self.side:<7} {self.kind:<9} {self.label}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "ts": self.ts,
            "side": self.side,
            "kind": self.kind,
            "label": self.label,
        }


def events(
    records: Iterable[StoredRecord], artefacts: Mapping[int, StoredArtefact] | None = None
) -> list[Event]:
    """One event per record, in chain order, worded by the side that wrote it.

    The side comes from the record's artefact type when `artefacts` is given (some alerts,
    such as the proxy's, do not name their server in the payload).
    """
    found: list[Event] = []
    for record in records:
        payload = _object(record.payload) or {}
        artefact = (artefacts or {}).get(record.artefact_id)
        side: Side | None = _SIDES.get(artefact.type, "other") if artefact is not None else None
        label: str | None = None
        if side in (None, "skills"):
            labelled = rail_label(record.kind, payload)
            if labelled is not None:
                label, side = labelled[1], "skills"
        if label is None and side in (None, "mcp"):
            label = mcp_label(record.kind, payload)
            if label is not None:
                side = "mcp"
        if label is None:
            label = _plain_label(record.kind, payload, artefact)
        found.append(Event(record.id, record.ts, side or "other", record.kind, label))
    return found


def _plain_label(kind: str, payload: Mapping[str, Any], artefact: StoredArtefact | None) -> str:
    """Words for a record neither side's labels cover: monitor events, the proxy's alerts."""
    name = payload.get("component") or (artefact.name if artefact is not None else "")
    code = payload.get("code")
    text = payload.get("detail") or payload.get("reason") or ""
    if kind == "alert" and isinstance(code, str):
        worded = code + (f" ({text})" if text else "")
        return f"{name}: {worded}" if name else worded
    return f"{name}: {kind}" if name else kind


def load_events(db: Path) -> list[Event]:
    """Every event in a store, read once."""
    with BaselineStore(db) as store:
        artefacts = {item.id: item for item in store.read_artefacts()}
        return events(store.read_records(), artefacts)


def select(
    found: Sequence[Event],
    *,
    since: str | None = None,
    kinds: Sequence[str] = (),
    side: str = "both",
    last: int = 0,
) -> list[Event]:
    """Filter events for `cim events`. `since` is a UTC time prefix, such as 2026-11-25T10."""
    chosen = [
        event
        for event in found
        if (since is None or event.ts >= since)
        and (not kinds or event.kind in kinds)
        and (side == "both" or event.side == side)
    ]
    return chosen[-last:] if last > 0 else chosen


def _skill_findings(board: SkillsBoard, records: Sequence[StoredRecord]) -> list[Finding]:
    """Changed skills, each with every change recorded for it (the board lists only the newest)."""
    changes: dict[str, list[str]] = {}
    for record in records:
        if record.kind != "integrity":
            continue
        payload = _object(record.payload)
        if payload is None or not isinstance(payload.get("skill_id"), str):
            continue
        change = f"{payload.get('change', 'change')} {payload.get('path', '')}".rstrip()
        changes.setdefault(str(payload["skill_id"]), []).append(change)
    found = []
    for row in board.skills:
        if row.integrity == "unchanged":
            continue
        listed = changes.get(row.skill_id) or ["removed"]
        found.append(Finding("skills", f"skill {row.skill_id}", tuple(listed), row.last_change_ts))
    return found


def _mcp_findings(summary: McpSummary) -> list[Finding]:
    found = []
    for (server, tool), changes in summary.changed_artefacts().items():
        name = f"mcp {server}/{tool}" if tool else f"mcp {server}"
        details = tuple(_without_prefix(c.detail, f"{tool}: ") for c in changes)
        found.append(Finding("mcp", name, details, changes[-1].ts))
    return found


def _collector_lines(status: Status) -> list[str]:
    watch = status.watch
    if watch is None:
        head = "cim watch has never run for this store"
    elif not watch.running:
        head = f"cim watch NOT RUNNING (last update {watch.updated or 'unknown'})"
    else:
        parts = [f"cim watch running since {watch.started}"]
        for child in watch.children:
            restarts = int(child.get("restarts") or 0)
            parts.append(
                f"{child.get('name')} {child.get('state')} ({_count(restarts, 'restart')})"
            )
        head = " · ".join(parts)
    lines = [f"collectors {head}"]
    live = [s for s in status.sessions if s.running]
    ended = [s for s in status.sessions if not s.running]
    if live:
        listed = ", ".join(f"{s.name} {s.subject} (pid {s.pid}, since {s.started})" for s in live)
        lines.append(f"           sessions: {listed}")
    if ended:
        listed = ", ".join(f"{s.name} {s.subject} (pid {s.pid})" for s in ended)
        lines.append(f"           ended without closing: {listed}")
    return lines


def _collectors(status: Status) -> dict[str, Any]:
    watch = status.watch
    return {
        "supervised": status.monitor_running,
        "watch": None
        if watch is None
        else {
            "pid": watch.pid,
            "running": watch.running,
            "started": watch.started,
            "updated": watch.updated,
            "children": list(watch.children),
        },
        "sessions": [
            {"name": s.name, "subject": s.subject, "pid": s.pid, "started": s.started}
            for s in status.sessions
            if s.running
        ],
        "ended_without_closing": [
            {"name": s.name, "subject": s.subject, "pid": s.pid}
            for s in status.sessions
            if not s.running
        ],
    }


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'s' * (number != 1)}"


def _without_prefix(text: str, prefix: str) -> str:
    return text[len(prefix) :] if prefix and text.startswith(prefix) else text


def _code(record: StoredRecord) -> str:
    payload = _object(record.payload)
    code = payload.get("code") if payload else None
    return code if isinstance(code, str) else ""


def _object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None
