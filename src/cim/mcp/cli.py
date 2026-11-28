"""MCP side of the `cim` CLI (T-13 decision 5: each side registers its own commands).

- `register(app)` adds MCP-only commands: `proxy`, `http-gateway`, `mcp-attack`
- `inventory_server`, `sweep_server`, `envelope_lines` are the MCP halves of the shared
  `cim inventory` / `sweep` / `envelope`

Hamza territory. Decision 7 (2026-11-25):
- `cim proxy --config cim.toml --server <id> -- <cmd>` reads `[mcp.servers.<id>]`
  and `[store].path`; flags and `CIM_PROXY_*` still win over the file.
- `cim http-gateway --config` auto-detects `cim.toml` vs the legacy JSON routes file.
- Proxy session file + gateway heartbeat: see `cim.mcp.runtime`.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

import typer

from cim.common.config import CimConfig, ConfigError, load_config
from cim.common.store import BaselineStore
from cim.mcp.drift import diff_tools, pinned_tools, record_sweep, server_artefact, write_pin
from cim.mcp.envelope import envelopes
from cim.mcp.http_gateway import load_gateway_config, run_gateway
from cim.mcp.inventory import hashable, load_tools_list, write_inventory
from cim.mcp.proxy import ProxyConfig, run_proxy

# Defaults of the original `cim inventory` (the HexStrike lab server).
DEFAULT_SERVER_ID = "hexstrike"
DEFAULT_NAME = "hexstrike"
DEFAULT_DESCRIPTION = "HexStrike MCP"
DEFAULT_ROOT = "/opt/mcp/hexstrike"
DEFAULT_MINIMUM = 150


def inventory_server(
    store: BaselineStore,
    *,
    tools_json: Path,
    server_id: str,
    name: str,
    description: str,
    root: str,
    origin: str,
    minimum: int,
    ts: str,
) -> tuple[str, bool]:
    """Baselines for one server from a recorded tools/list (T-07). Returns (line, chain ok)."""
    tools = load_tools_list(tools_json)
    result = write_inventory(
        store,
        server_id=server_id,
        name=name,
        description=description,
        root=root,
        origin=origin,
        tools=tools,
        ts=ts,
        minimum=minimum,
    )
    pinned_now = pinned_tools(store, server_id) is None
    if pinned_now:  # the first inventory of a server is its reference for `cim sweep`
        write_pin(
            store,
            server_id=server_id,
            origin=origin,
            tools=hashable(tools),
            ts=ts,
            server_artefact_id=result.server_artefact_id,
        )
    status = store.verify_chain()
    line = (
        f"inventory: server={server_id} tools={len(result.tool_digests)} "
        f"manifest={result.manifest_digest[:12]}… chain={'ok' if status.ok else 'broken'} "
        f"pin={'written' if pinned_now else 'kept'}"
    )
    return line, status.ok


def sweep_server(
    store: BaselineStore, *, tools_json: Path, server_id: str, ts: str
) -> tuple[list[str], int]:
    """Re-read a tools/list and record drift against the pin (T-12). Returns (lines, exit code)."""
    current = hashable(load_tools_list(tools_json))
    pin = pinned_tools(store, server_id)
    if pin is None:
        return [f"sweep: no pin for {server_id}; run inventory or the proxy first"], 2
    artefact_id = server_artefact(store, server_id)
    if artefact_id is None:
        artefact_id = store.get_or_create_artefact("mcp_server", server_id, "sweep")
    recorded = record_sweep(
        store,
        server_id=server_id,
        server_artefact_id=artefact_id,
        pinned=pin,
        current=current,
        ts=ts,
    )
    differences = diff_tools(pin, current)
    lines = [f"sweep: {drift.detail}" for drift in recorded]
    if not recorded and differences:
        lines.append(
            f"sweep: {server_id} still differs from the pin "
            f"({len(differences)} differences, already recorded)"
        )
    elif not recorded:
        lines.append(f"sweep: {server_id} unchanged")
    return lines, 0


def envelope_lines(db: Path, server_id: str, tool: str | None = None) -> list[str]:
    """Per-tool behavioural features (T-14); empty when the server has no observations."""
    return [row.render() for row in envelopes(db, server_id, tool)]


def observed_servers(db: Path) -> list[str]:
    """Servers with at least one observation, for `cim envelope` without `--server-id`."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT DISTINCT server_id FROM envelope_obs ORDER BY server_id")
        return [str(row[0]) for row in rows]
    except sqlite3.OperationalError:
        return []  # no MCP observations table: nothing was proxied into this store
    finally:
        con.close()


def resolve_proxy_config(
    *,
    config_path: Path | None = None,
    server: str | None = None,
    db: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> ProxyConfig:
    """Build ``ProxyConfig`` with flag > env > cim.toml > default (T-13 §4 / decision 7).

    Accepted ``[mcp.servers.<id>]`` keys (Fasih loader): ``root``, ``origin``,
    ``tools_list``, ``minimum_tools``. Proxy uses ``root`` and ``origin``;
    ``tools_list`` / ``minimum_tools`` stay for offline inventory/sweep.
    """
    source = os.environ if env is None else env
    base = ProxyConfig.from_env(source)
    try:
        cim: CimConfig = load_config(config_path, env=source)
    except ConfigError as exc:
        raise ValueError(str(exc)) from None

    server_id = server or base.server_id
    root = base.root
    origin = base.origin
    store_db = base.db

    # File values apply only when env left the default (flag/env already in `base`).
    if "CIM_PROXY_DB" not in source:
        store_db = cim.store_path
    named = cim.server(server_id)
    if named is not None:
        if "CIM_PROXY_ROOT" not in source:
            root = named.root
        if "CIM_PROXY_ORIGIN" not in source:
            origin = named.origin or cim.store.origin
        if server is not None or "CIM_PROXY_SERVER_ID" not in source:
            server_id = server or server_id
    elif server is not None and config_path is not None:
        # Explicit --server with a config that does not name it: still use the id;
        # root/origin stay at env/defaults (operator may pass a one-off command).
        server_id = server

    if db is not None:
        store_db = db
    if server is not None:
        server_id = server

    return ProxyConfig(db=store_db, server_id=server_id, origin=origin, root=root)


def register(app: typer.Typer) -> None:
    """Add the MCP-only commands to the shared `cim` app."""
    app.command(
        "proxy",
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    )(proxy)
    app.command("http-gateway")(http_gateway)
    app.command("mcp-attack")(mcp_attack)


def proxy(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            help="cim.toml (default discovery: $CIM_CONFIG, ./cim.toml, ~/.config/cim/cim.toml)",
        ),
    ] = None,
    server: Annotated[
        str | None,
        typer.Option(
            "--server",
            help="\\[mcp.servers.<id>] to bind (default: hexstrike / env)",
        ),
    ] = None,
    db: Annotated[
        Path | None,
        typer.Option(
            "--db",
            help="Baseline store path (default: \\[store].path / $CIM_PROXY_DB)",
        ),
    ] = None,
) -> None:
    """Run an MCP server behind the capture proxy: cim proxy [--config] [--server] -- <cmd>.

    stdout carries the MCP stream, so this command never prints to it.
    """
    command = [arg for arg in ctx.args if arg != "--"]
    if not command:
        typer.echo("proxy: missing server command after --", err=True)
        raise typer.Exit(code=2)
    try:
        proxy_config = resolve_proxy_config(config_path=config, server=server, db=db)
    except ValueError as exc:
        typer.echo(f"cim proxy: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    raise typer.Exit(code=run_proxy(command, proxy_config, sys.stdin.buffer, sys.stdout.buffer))


def http_gateway(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            exists=True,
            dir_okay=False,
            readable=True,
            help="cim.toml with \\[mcp.gateway], or legacy JSON routes file (auto-detected)",
        ),
    ],
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Baseline store path (overrides config db)"),
    ] = None,
    host: Annotated[str | None, typer.Option("--host")] = None,
    port: Annotated[int | None, typer.Option("--port", min=1, max=65535)] = None,
) -> None:
    """Proxy Cursor URL / Streamable-HTTP MCPs into the baseline store (T-16b).

    Point Cursor at http://127.0.0.1:<port>/s/<server-id> instead of the real URL.
    Authorization headers are forwarded and never logged.

    Decision 7: ``--config`` means the same thing as elsewhere when the file is
    ``cim.toml``; a JSON routes file (``config/cursor-http-gateway.json``) still works.
    """
    try:
        loaded = load_gateway_config(config, db=db, host=host, port=port)
    except ValueError as exc:
        typer.echo(f"cim http-gateway: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    raise typer.Exit(code=run_gateway(loaded))


def mcp_attack(
    attack: Annotated[Literal["A1", "A2"], typer.Argument(help="A1 rug-pull or A2 trigger")],
    work: Annotated[
        Path,
        typer.Option("--work", help="Empty working directory for the attack store and fixtures"),
    ],
    warmup: Annotated[int, typer.Option("--warmup", min=1)] = 30,
) -> None:
    """T-17 MCP attack pack: A1 schema rug-pull, A2 behavioural trigger (stand-in server)."""
    from cim.mcp.attacks import run_a1, run_a2

    work.mkdir(parents=True, exist_ok=True)
    report = run_a1(work) if attack == "A1" else run_a2(work, warmup=warmup)
    typer.echo(report.render())
    raise typer.Exit(code=0 if report.passed else 1)
