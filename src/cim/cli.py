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
from cim.dashboard.board import load_board
from cim.dashboard.page import render_page
from cim.dashboard.serve import make_server
from cim.mcp.drift import diff_tools, pinned_tools, record_sweep, server_artefact, write_pin
from cim.mcp.envelope import envelopes
from cim.mcp.http_gateway import load_gateway_config, run_gateway
from cim.mcp.inventory import hashable, load_tools_list, write_inventory
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
        pinned_now = pinned_tools(store, server_id) is None
        if pinned_now:  # the first inventory of a server is its reference for `cim sweep`
            write_pin(store, server_id=server_id, origin=origin, tools=hashable(tools), ts=ts)
        status = store.verify_chain()
    typer.echo(
        f"inventory: server={server_id} tools={len(result.tool_digests)} "
        f"manifest={result.manifest_digest[:12]}… chain={'ok' if status.ok else 'broken'} "
        f"pin={'written' if pinned_now else 'kept'}"
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


@app.command("http-gateway")
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


@app.command("sweep")
def sweep(
    db: Annotated[Path, typer.Option("--db", exists=True, dir_okay=False, readable=True)],
    tools_json: Annotated[
        Path,
        typer.Option("--tools-json", exists=True, dir_okay=False, readable=True),
    ],
    server_id: Annotated[str, typer.Option("--server-id")] = "hexstrike",
) -> None:
    """Re-read a tools/list and record schema drift against the pinned baseline (T-12)."""
    current = hashable(load_tools_list(tools_json))
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with BaselineStore(db) as store:
        pin = pinned_tools(store, server_id)
        if pin is None:
            typer.echo(f"sweep: no pin for {server_id}; run inventory or the proxy first")
            raise typer.Exit(code=2)
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
    for drift in recorded:
        typer.echo(f"sweep: {drift.detail}")
    if not recorded and differences:
        typer.echo(
            f"sweep: {server_id} still differs from the pin "
            f"({len(differences)} differences, already recorded)"
        )
    elif not recorded:
        typer.echo(f"sweep: {server_id} unchanged")


@app.command("envelope")
def envelope(
    db: Annotated[Path, typer.Option("--db", exists=True, dir_okay=False, readable=True)],
    server_id: Annotated[str, typer.Option("--server-id")] = "hexstrike",
    tool: Annotated[str | None, typer.Option("--tool")] = None,
) -> None:
    """Show per-tool behavioural features and whether warm-up is done (T-14)."""
    rows = envelopes(db, server_id, tool)
    if not rows:
        typer.echo(f"envelope: no observations for {server_id}")
        raise typer.Exit(code=2)
    for row in rows:
        typer.echo(row.render())


@app.command("verify-chain")
def verify_chain(
    db: Annotated[
        Path,
        typer.Option("--db", exists=True, dir_okay=False, readable=True),
    ],
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
    with BaselineStore(db) as store:
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
    typer.echo(f"verify-chain: ok ({result.count} records) tip={result.tip}")


if __name__ == "__main__":
    app()
