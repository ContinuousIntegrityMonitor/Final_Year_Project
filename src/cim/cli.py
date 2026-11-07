"""cim CLI entrypoint."""

from __future__ import annotations

import dataclasses
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from cim import __version__
from cim.common.store import BaselineStore
from cim.mcp.inventory import load_tools_list, write_inventory
from cim.mcp.proxy import ProxyConfig, run_proxy

app = typer.Typer(
    name="cim",
    help="Continuous Integrity Monitor - inventory, watch, status, verify-chain.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """CIM command group."""


@app.command("version")
def version() -> None:
    """Print package version."""
    typer.echo(f"cim {__version__}")


@app.command("status")
def status() -> None:
    """Show monitor status (stub until T-13)."""
    typer.echo("status: not implemented (awaiting T-13 pipeline integration)")


@app.command("inventory")
def inventory(
    db: Annotated[
        Path,
        typer.Option("--db", help="Baseline store SQLite path (created if missing)"),
    ],
    tools_json: Annotated[
        Path,
        typer.Option(
            "--tools-json",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Recorded MCP tools/list JSON (list or {tools:[...]})",
        ),
    ],
    server_id: Annotated[str, typer.Option("--server-id")] = "hexstrike",
    name: Annotated[str, typer.Option("--name")] = "hexstrike",
    description: Annotated[str, typer.Option("--description")] = "HexStrike MCP",
    root: Annotated[str, typer.Option("--root")] = "/opt/mcp/hexstrike",
    origin: Annotated[str, typer.Option("--origin")] = "vm-mon",
    minimum: Annotated[
        int,
        typer.Option("--minimum", help="Minimum tool count (HexStrike lab = 150)"),
    ] = 150,
) -> None:
    """Write MCP server + tool artefact baselines from a recorded tools/list (T-07)."""
    tools = load_tools_list(tools_json)
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with BaselineStore(db) as store:
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
        status = store.verify_chain()
    typer.echo(
        f"inventory: server={server_id} tools={len(result.tool_digests)} "
        f"manifest={result.manifest_digest[:12]}… chain={'ok' if status.ok else 'broken'}"
    )
    if not status.ok:
        raise typer.Exit(code=1)


@app.command(
    "proxy",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
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


@app.command("verify-chain")
def verify_chain(
    db: Annotated[
        Path,
        typer.Option("--db", exists=True, dir_okay=False, readable=True),
    ],
) -> None:
    """Recompute the baseline hash chain. Exit 1 if any historical row was changed."""
    with BaselineStore(db) as store:
        result = store.verify_chain()
    if result.ok:
        typer.echo(f"verify-chain: ok ({result.count} records)")
        raise typer.Exit(code=0)
    typer.echo(f"verify-chain: broken at record {result.broken_at}: {result.reason}")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
