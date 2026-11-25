"""Skills side of the `cim` CLI (T-13 decision 5: each side registers its own commands).

- `inventory_lines`, `sweep_lines` and `envelope_lines` are the skills halves of the shared
  `cim inventory`, `cim sweep` and `cim envelope` (the line formats of `python -m cim.skills`,
  except that an unchanged sweep says `sweep: skills unchanged`, beside the MCP lines);
- `register(app)` adds `cim skills ...`, which hands its arguments unchanged to the skills
  tools (`python -m cim.skills`): corpus, inventory, sweep, watch, observe, exec, envelope,
  board, attack.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import typer

from cim.common.store import BaselineStore
from cim.skills.envelope import profiles
from cim.skills.inventory import SweepResult, sweep, take_inventory, write_baselines


def inventory_lines(store: BaselineStore, roots: Sequence[Path], origin: str) -> tuple[str, bool]:
    """Baselines for every skill under the roots. Returns (line, chain ok)."""
    found = take_inventory(list(roots))
    written = write_baselines(store, found, origin=origin)
    chain = store.verify_chain()
    line = (
        f"inventory: skills={len(found)} new_baselines={len(written)} "
        f"chain={'ok' if chain.ok else 'broken'}"
    )
    return line, chain.ok


def sweep_lines(result: SweepResult, *, quiet_when_unchanged: bool = False) -> list[str]:
    """What one skills sweep recorded, one line per new skill or change."""
    lines = [f"sweep: new skill {skill_id}" for skill_id in result.new_skills]
    for event in result.events:
        source = f" (was {event.old_path})" if event.old_path else ""
        lines.append(f"sweep: {event.skill_id}: {event.change} {event.path}{source}")
    if not quiet_when_unchanged and not lines:
        lines.append("sweep: skills unchanged")
    return lines


def sweep_store(store: BaselineStore, roots: Sequence[Path], origin: str) -> list[str]:
    """Sweep the roots against the stored baselines and say what was recorded."""
    return sweep_lines(sweep(store, list(roots), origin=origin))


def envelope_lines(store: BaselineStore, skill_id: str | None = None) -> list[str]:
    """Each skill's behavioural profile; empty when the store has no skill runs."""
    return [profile.render() for profile in profiles(store, skill_id)]


def register(app: typer.Typer) -> None:
    """Add `cim skills ...` to the shared `cim` app."""
    app.command(
        "skills",
        context_settings={
            "allow_extra_args": True,
            "ignore_unknown_options": True,
            "help_option_names": [],  # `cim skills --help` is the skills tools' own help
        },
        help="Skills-only tools: corpus, observe, exec, attack, board, watch, ... "
        "(`cim skills --help` lists them).",
    )(skills)


def skills(ctx: typer.Context) -> None:
    """Hand the arguments to `python -m cim.skills` and exit with its status."""
    from cim.skills.__main__ import main

    try:
        code = main(list(ctx.args))
    except SystemExit as stop:  # argparse usage errors and --help
        code = stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 2)
        if isinstance(stop.code, str):
            typer.echo(stop.code, err=True)
    raise typer.Exit(code=code)
