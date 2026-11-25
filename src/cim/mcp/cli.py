"""MCP side of the `cim` CLI (T-13 decision 5: each side registers its own commands).

Moved here from `cim/cli.py` without changing what they do:
- `register(app)` adds the MCP-only commands, `cim proxy` and `cim http-gateway`;
- `inventory_server`, `sweep_server` and `envelope_lines` are the MCP halves of the shared
  `cim inventory`, `cim sweep` and `cim envelope`, which `cim/cli.py` calls for each server.

Hamza's territory. The `--config` / `--server` handling for proxy and gateway is his (T-13
decision 7); nothing here reads `cim.toml` yet.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import sys
from pathlib import Path
from typing import Annotated

import typer

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


def register(app: typer.Typer) -> None:
    """Add the MCP-only commands to the shared `cim` app."""
    app.command(
        "proxy",
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    )(proxy)
    app.command("http-gateway")(http_gateway)


def proxy(
    ctx: typer.Context,
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Baseline store path (default: $CIM_PROXY_DB)"),
    ] = None,
) -> None:
    """Run an MCP server behind the capture proxy: cim proxy --db store.sqlite -- <server cmd>.

    stdout carries the MCP stream, so this command never prints to it.
    """
    command = [arg for arg in ctx.args if arg != "--"]
    if not command:
        typer.echo("proxy: missing server command after --", err=True)
        raise typer.Exit(code=2)
    config = ProxyConfig.from_env()
    if db is not None:
        config = dataclasses.replace(config, db=db)
    raise typer.Exit(code=run_proxy(command, config, sys.stdin.buffer, sys.stdout.buffer))


def http_gateway(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            exists=True,
            dir_okay=False,
            readable=True,
            help="JSON routes file (see config/cursor-http-gateway.json)",
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
    """
    try:
        loaded = load_gateway_config(config, db=db, host=host, port=port)
    except ValueError as exc:
        typer.echo(f"cim http-gateway: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    raise typer.Exit(code=run_gateway(loaded))
