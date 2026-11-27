"""cim CLI entrypoint (border file: both review).

T-13 decision 5 (docs/T13_PIPELINE_DESIGN.md, section 5): this file builds the commands both
sides share and mounts each side's own commands from that side's module, so neither edits the
other's commands to add its own.

- Shared, here: `version`, `init`, `inventory`, `sweep`, `envelope`, `status`, `events`,
  `watch`, `verify-chain`, `dashboard`. `inventory`, `sweep` and `envelope` cover both sides: skills
  for the configured skill roots, MCP for each configured server, or for the one named on the
  command line.
- MCP, from `cim.mcp.cli`: `proxy`, `http-gateway`.
- Skills, from `cim.skills.cli`: `cim skills ...` (corpus, observe, exec, attack, board, ...).

Settings come from `cim.toml` (`cim.common.config`): flag > environment > file > default. Every
command that worked before keeps working with the same flags and the same output.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from cim import __version__
from cim.common import status as monitor_status
from cim.common import watchdog
from cim.common.config import CimConfig, ConfigError, load_config, starter_toml
from cim.common.runtime import read_watch_state
from cim.common.store import BaselineStore
from cim.dashboard.board import load_board
from cim.dashboard.page import render_page
from cim.dashboard.serve import make_server
from cim.mcp import cli as mcp_cli
from cim.skills import cli as skills_cli

app = typer.Typer(
    name="cim",
    help="Continuous Integrity Monitor - inventory, watch, status, verify-chain.",
    no_args_is_help=True,
)


class Side(StrEnum):
    both = "both"
    skills = "skills"
    mcp = "mcp"


ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        help="cim.toml to read (default: $CIM_CONFIG, ./cim.toml, ~/.config/cim/cim.toml)",
    ),
]
DbOption = Annotated[
    Path | None, typer.Option("--db", help="Baseline store path (default: \\[store].path)")
]
SkillRootOption = Annotated[
    list[Path] | None,
    typer.Option(
        "--skill-root",
        help="Skill root, repeatable (default: $CIM_SKILL_ROOTS, then \\[skills].roots)",
    ),
]
SideOption = Annotated[Side, typer.Option("--side", help="Which side to cover")]
FOLLOW_POLL_S = 1.0


@app.callback()
def main() -> None:
    """CIM command group."""


mcp_cli.register(app)
skills_cli.register(app)


def _settings(path: Path | None) -> CimConfig:
    try:
        return load_config(path)
    except ConfigError as exc:
        typer.echo(f"cim: {exc}", err=True)
        raise typer.Exit(code=2) from exc


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _existing_store(db: Path, command: str) -> Path:
    if not db.is_file():  # reading or sweeping must not create a store
        typer.echo(f"{command}: no store at {db}; run cim inventory first", err=True)
        raise typer.Exit(code=2)
    return db


def _skill_roots(flags: Sequence[Path] | None, config: CimConfig) -> tuple[Path, ...]:
    return tuple(flags) if flags else config.skills.roots


def _mcp_targets(
    config: CimConfig, tools_json: Path | None, server_id: str | None, command: str
) -> list[tuple[str, Path]]:
    """(server id, tools/list file) pairs: the one on the command line, or the configured ones."""
    if tools_json is not None:
        return [(server_id or mcp_cli.DEFAULT_SERVER_ID, tools_json)]
    listed = {
        name: server.tools_list
        for name, server in config.mcp.servers.items()
        if server.tools_list is not None
    }
    if server_id is not None:
        if server_id not in listed:
            typer.echo(
                f"{command}: no tools list for {server_id}: give --tools-json or set "
                f"[mcp.servers.{server_id}].tools_list",
                err=True,
            )
            raise typer.Exit(code=2)
        return [(server_id, listed[server_id])]
    return sorted(listed.items())


def _nothing_to_do(command: str, side: Side) -> None:
    wanted = []
    if side is not Side.mcp:
        wanted.append("skill roots (--skill-root, $CIM_SKILL_ROOTS or [skills].roots)")
    if side is not Side.skills:
        wanted.append("MCP tools list (--tools-json or [mcp.servers.<id>].tools_list)")
    typer.echo(f"{command}: nothing to do: no {' and no '.join(wanted)}", err=True)
    raise typer.Exit(code=2)


@app.command("version")
def version() -> None:
    """Print package version."""
    typer.echo(f"cim {__version__}")


@app.command("init")
def init(
    path: Annotated[Path, typer.Argument(help="Where to write it")] = Path("cim.toml"),
    db: Annotated[Path, typer.Option("--db", help="Store path to write in")] = Path(
        "logs/cim-store.sqlite"
    ),
    origin: Annotated[str, typer.Option("--origin", help="Host name for artefacts")] = "vm-mon",
    skill_root: Annotated[
        list[Path] | None, typer.Option("--skill-root", help="Skill root, repeatable")
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing file")] = False,
    systemd: Annotated[
        bool,
        typer.Option(
            "--systemd", help="Also print a systemd user unit that runs cim watch on this file"
        ),
    ] = False,
) -> None:
    """Write a starter cim.toml: store path, origin and skill roots (T-13)."""
    if systemd and path.exists() and not force:
        typer.echo(systemd_unit(path))  # the file is there already: print the unit only
        return
    if path.exists() and not force:
        typer.echo(f"init: {path} exists; pass --force to replace it", err=True)
        raise typer.Exit(code=1)
    roots = tuple(root.expanduser().resolve() for root in skill_root or ())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(starter_toml(store=db, origin=origin, roots=roots), encoding="utf-8")
    # With --systemd, stdout is the unit (to redirect into a file), so the note goes to stderr.
    typer.echo(
        f"init: wrote {path} (store {db}, origin {origin}, {len(roots)} skill root(s))",
        err=systemd,
    )
    if systemd:
        typer.echo(systemd_unit(path))


def systemd_unit(config: Path) -> str:
    """A systemd user unit for `cim watch` (systemd restarts it; it restarts the collectors)."""
    where = config.expanduser().resolve()
    return f"""# ~/.config/systemd/user/cim-watch.service
# systemctl --user daemon-reload && systemctl --user enable --now cim-watch
[Unit]
Description=CIM monitor (cim watch)

[Service]
ExecStart={sys.executable} -m cim watch --config {where}
WorkingDirectory={where.parent}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target"""


@app.command("status")
def status(
    config_path: ConfigOption = None,
    db: DbOption = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON instead of lines")] = False,
    require_watch: Annotated[
        bool, typer.Option("--require-watch", help="Exit 2 unless cim watch is running")
    ] = False,
) -> None:
    """C5: store and chain, collectors, inventory, findings, alerts, learning state.

    Exit 0 when clean; 1 when the chain is broken or anything was found; 2 when the monitor is
    not running (cim watch ran for this store and has stopped; or never ran, with
    --require-watch), or when there is no store.
    """
    path = _existing_store(db or _settings(config_path).store_path, "status")
    found = monitor_status.load_status(path)
    if as_json:
        typer.echo(json.dumps(monitor_status.as_dict(found), indent=2))
    else:
        for line in monitor_status.render(found):
            typer.echo(line)
    code = found.exit_code(require_watch=require_watch)
    if code:
        raise typer.Exit(code=code)


@app.command("watch")
def watch(config_path: ConfigOption = None, db: DbOption = None) -> None:
    """Supervise the collectors until stopped: the skills watcher and, if configured, the gateway.

    Restarts a child that exits or whose heartbeat stops, with backoff, and records each
    restart in the chain (`collector_restarted`, `collector_failed`). Ctrl-C or SIGTERM stops
    the children too. On VM-MON run it under systemd (`cim init --systemd`).
    """
    config = _settings(config_path)
    store = db or config.store_path
    children = watchdog.children_for(config, store=store)
    if not children:
        typer.echo(
            "watch: nothing to supervise: set [skills].roots (or $CIM_SKILL_ROOTS) "
            "or [mcp.gateway] in cim.toml",
            err=True,
        )
        raise typer.Exit(code=2)
    current = read_watch_state(store)
    if current is not None and current.running and current.pid != os.getpid():
        typer.echo(f"watch: already running for {store} (pid {current.pid})", err=True)
        raise typer.Exit(code=1)
    store.parent.mkdir(parents=True, exist_ok=True)
    supervisor = watchdog.Supervisor(
        store,
        children,
        origin=config.store.origin,
        heartbeat_s=config.watchdog.heartbeat_s,
        backoff_max_s=config.watchdog.backoff_max_s,
        max_restarts=config.watchdog.max_restarts,
    )
    stop = threading.Event()
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_args: stop.set())
    names = ", ".join(child.name for child in children)
    typer.echo(f"watch: supervising {names}; store {store}", err=True)
    try:
        supervisor.run(stop)
    except KeyboardInterrupt:
        stop.set()  # run() stops the children on its way out


class EventSide(StrEnum):
    both = "both"
    skills = "skills"
    mcp = "mcp"
    monitor = "monitor"


class EventKind(StrEnum):
    artefact = "artefact"
    integrity = "integrity"
    behaviour = "behaviour"
    alert = "alert"


@app.command("events")
def events(
    config_path: ConfigOption = None,
    db: DbOption = None,
    since: Annotated[
        str | None,
        typer.Option("--since", help="UTC time or prefix, e.g. 2026-11-25 or 2026-11-25T10:30"),
    ] = None,
    kind: Annotated[
        list[EventKind] | None, typer.Option("--kind", help="Record kind, repeatable")
    ] = None,
    side: Annotated[EventSide, typer.Option("--side")] = EventSide.both,
    last: Annotated[int, typer.Option("--last", min=0, help="Only the newest N (0: all)")] = 50,
    follow: Annotated[
        bool, typer.Option("--follow", "-f", help="Keep printing new records until Ctrl-C")
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="One JSON object per line")] = False,
) -> None:
    """One line per store record, newest last, worded by the side that wrote it."""
    path = _existing_store(db or _settings(config_path).store_path, "events")
    kinds = [str(item) for item in kind or ()]

    def show(found: list[monitor_status.Event]) -> None:
        for event in found:
            typer.echo(json.dumps(event.as_dict()) if as_json else event.render())

    with BaselineStore(path) as store:
        artefacts = {item.id: item for item in store.read_artefacts()}
        every = monitor_status.events(store.read_records(), artefacts)
        show(monitor_status.select(every, since=since, kinds=kinds, side=str(side), last=last))
        seen = every[-1].record_id if every else 0
        try:
            while follow:
                time.sleep(FOLLOW_POLL_S)
                fresh = [r for r in store.read_records() if r.id > seen]
                if fresh:
                    seen = fresh[-1].id
                    artefacts = {item.id: item for item in store.read_artefacts()}
                    new = monitor_status.events(fresh, artefacts)
                    show(monitor_status.select(new, since=since, kinds=kinds, side=str(side)))
        except KeyboardInterrupt:
            pass


@app.command("dashboard")
def dashboard(
    db: Annotated[
        Path,
        typer.Option("--db", exists=True, dir_okay=False, readable=True),
    ],
    port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8765,
    once: Annotated[
        bool,
        typer.Option("--once", help="Print the page once and exit"),
    ] = False,
    demo: Annotated[
        bool,
        typer.Option(
            "--demo",
            help="Enable demo write buttons (clear/tamper/call); requires a token",
        ),
    ] = False,
    demo_token: Annotated[
        str,
        typer.Option(
            "--demo-token",
            help="Shared secret for demo writes (auto-generated when --demo and omitted)",
            envvar="CIM_DASHBOARD_DEMO_TOKEN",
        ),
    ] = "",
) -> None:
    """Open a page for one store: chain, tools, changes, calls. Read-only unless --demo."""
    if once:
        typer.echo(render_page(load_board(db)))
        return
    server = make_server(
        db,
        "127.0.0.1",
        port,
        demo=demo,
        demo_token=demo_token or None,
    )
    bound = server.server_address[1]
    typer.echo(f"dashboard: http://127.0.0.1:{bound}")
    if demo:
        token = getattr(server, "cim_demo_token", "")
        typer.echo(f"demo token: {token}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


@app.command("inventory")
def inventory(
    config_path: ConfigOption = None,
    db: DbOption = None,
    side: SideOption = Side.both,
    skill_root: SkillRootOption = None,
    tools_json: Annotated[
        Path | None,
        typer.Option(
            "--tools-json",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Recorded MCP tools/list JSON (list or {tools:[...]}); "
            "default: each \\[mcp.servers.<id>].tools_list",
        ),
    ] = None,
    server_id: Annotated[str | None, typer.Option("--server-id")] = None,
    name: Annotated[str | None, typer.Option("--name")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    root: Annotated[str | None, typer.Option("--root", help="MCP server root")] = None,
    origin: Annotated[str | None, typer.Option("--origin")] = None,
    minimum: Annotated[
        int | None,
        typer.Option("--minimum", help="Minimum tool count (HexStrike lab = 150)"),
    ] = None,
) -> None:
    """Store baselines: every skill under the skill roots, and each MCP server's tools (T-07).

    One line per skills inventory and per MCP server. The first inventory of a server also
    pins it, as the reference for `cim sweep`.
    """
    config = _settings(config_path)
    roots = _skill_roots(skill_root, config) if side is not Side.mcp else ()
    targets = (
        _mcp_targets(config, tools_json, server_id, "inventory") if side is not Side.skills else []
    )
    if not roots and not targets:
        _nothing_to_do("inventory", side)
    ok = True
    ts = _now()
    path = db or config.store_path
    path.parent.mkdir(parents=True, exist_ok=True)  # the first inventory creates the store
    with BaselineStore(path) as store:
        if roots:
            line, chain = skills_cli.inventory_lines(store, roots, origin or config.store.origin)
            typer.echo(line)
            ok &= chain
        for target_id, listed in targets:
            server = config.server(target_id)
            line, chain = mcp_cli.inventory_server(
                store,
                tools_json=listed,
                server_id=target_id,
                name=name or (target_id if server else mcp_cli.DEFAULT_NAME),
                description=description
                or (f"{target_id} MCP" if server else mcp_cli.DEFAULT_DESCRIPTION),
                root=root or (server.root if server else mcp_cli.DEFAULT_ROOT),
                origin=origin or (server.origin if server else None) or config.store.origin,
                minimum=minimum
                if minimum is not None
                else (server.minimum_tools if server else mcp_cli.DEFAULT_MINIMUM),
                ts=ts,
            )
            typer.echo(line)
            ok &= chain
    if not ok:
        raise typer.Exit(code=1)


@app.command("sweep")
def sweep(
    config_path: ConfigOption = None,
    db: DbOption = None,
    side: SideOption = Side.both,
    skill_root: SkillRootOption = None,
    tools_json: Annotated[
        Path | None,
        typer.Option(
            "--tools-json",
            exists=True,
            dir_okay=False,
            readable=True,
            help="MCP tools/list to compare with the pin (default: each configured tools_list)",
        ),
    ] = None,
    server_id: Annotated[str | None, typer.Option("--server-id")] = None,
    origin: Annotated[str | None, typer.Option("--origin")] = None,
) -> None:
    """Record what changed since the baselines: skill files (T-08) and MCP tool schemas (T-12)."""
    config = _settings(config_path)
    roots = _skill_roots(skill_root, config) if side is not Side.mcp else ()
    targets = (
        _mcp_targets(config, tools_json, server_id, "sweep") if side is not Side.skills else []
    )
    if not roots and not targets:
        _nothing_to_do("sweep", side)
    code = 0
    ts = _now()
    with BaselineStore(_existing_store(db or config.store_path, "sweep")) as store:
        if roots:
            for line in skills_cli.sweep_store(store, roots, origin or config.store.origin):
                typer.echo(line)
        for target_id, listed in targets:
            lines, status_code = mcp_cli.sweep_server(
                store, tools_json=listed, server_id=target_id, ts=ts
            )
            for line in lines:
                typer.echo(line)
            code = max(code, status_code)
    if code:
        raise typer.Exit(code=code)


@app.command("envelope")
def envelope(
    config_path: ConfigOption = None,
    db: DbOption = None,
    side: SideOption = Side.both,
    server_id: Annotated[
        str | None, typer.Option("--server-id", help="One MCP server (default: all observed)")
    ] = None,
    tool: Annotated[str | None, typer.Option("--tool", help="One MCP tool")] = None,
    skill: Annotated[str | None, typer.Option("--skill", help="One skill")] = None,
) -> None:
    """Show behavioural profiles and whether warm-up is done: MCP tools (T-14), skills (T-15)."""
    config = _settings(config_path)
    path = _existing_store(db or config.store_path, "envelope")
    lines: list[str] = []
    if side is not Side.skills:
        servers = [server_id] if server_id is not None else mcp_cli.observed_servers(path)
        for name in servers:
            lines += mcp_cli.envelope_lines(path, name, tool)
    if side is not Side.mcp:
        with BaselineStore(path) as store:
            lines += skills_cli.envelope_lines(store, skill)
    if not lines:
        wanted = server_id or skill
        typer.echo(f"envelope: no observations{f' for {wanted}' if wanted else ''}")
        raise typer.Exit(code=2)
    for line in lines:
        typer.echo(line)


@app.command("verify-chain")
def verify_chain(
    config_path: ConfigOption = None,
    db: DbOption = None,
    expect_tip: Annotated[
        str | None,
        typer.Option("--expect-tip", help="Fail unless the last record has this hash"),
    ] = None,
    min_count: Annotated[
        int | None,
        typer.Option("--min-count", min=0, help="Fail if the store holds fewer records"),
    ] = None,
) -> None:
    """Recompute the baseline hash chain. Exit 1 if any historical row was changed.

    A chain that was cut short, or rebuilt from scratch, still verifies on its own. Note the
    tip and count this command prints somewhere outside the store, and pass them back with
    --expect-tip / --min-count to catch that as well.
    """
    path = _existing_store(db or _settings(config_path).store_path, "verify-chain")
    with BaselineStore(path) as store:
        result = store.verify_chain()
    if not result.ok:
        typer.echo(f"verify-chain: broken at record {result.broken_at}: {result.reason}")
        raise typer.Exit(code=1)
    if min_count is not None and result.count < min_count:
        typer.echo(f"verify-chain: records are missing: {result.count} found, {min_count} expected")
        raise typer.Exit(code=1)
    if expect_tip is not None and result.tip != expect_tip.lower():
        typer.echo(f"verify-chain: tip is {result.tip}, not the expected {expect_tip.lower()}")
        raise typer.Exit(code=1)
    if result.hash_version == 1:
        typer.echo(
            f"verify-chain: ok ({result.count} records, "
            f"hash v1: ts and artefacts not covered) tip={result.tip}"
        )
    else:
        typer.echo(f"verify-chain: ok ({result.count} records) tip={result.tip}")


if __name__ == "__main__":
    app()
