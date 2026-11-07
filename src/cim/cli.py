"""cim CLI entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cim import __version__
from cim.common.store import BaselineStore

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
