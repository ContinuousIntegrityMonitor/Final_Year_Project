"""cim CLI entrypoint (v0 stub for T-01)."""

from __future__ import annotations

import typer

from cim import __version__

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


if __name__ == "__main__":
    app()
