"""Skills-side commands: python -m cim.skills <command>.

These stay here, not in the shared `cim` CLI, until pipeline integration (T-13).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cim.common.store import BaselineStore
from cim.skills.collector import observe, record_behaviour, tracer_available
from cim.skills.corpus import (
    default_root,
    load_manifest,
    run_corpus,
    update_manifest,
    verify_manifest,
)
from cim.skills.envelope import profiles
from cim.skills.inventory import (
    DEFAULT_ORIGIN,
    SweepResult,
    skill_roots,
    sweep,
    take_inventory,
    write_baselines,
)
from cim.skills.runner import discover_skills
from cim.skills.scoped import scope_available
from cim.skills.watcher import DEFAULT_INTERVAL_S, watch


def _corpus(args: argparse.Namespace) -> int:
    root: Path = args.root or default_root()
    if args.action == "update":
        unlabelled = update_manifest(root)
        print(f"corpus: manifest written for {root}")
        for skill_id in unlabelled:
            print(f"corpus: {skill_id} is new: set its label and run arguments by hand")
        return 0
    if args.action == "verify":
        problems = verify_manifest(root)
        for problem in problems:
            print(f"corpus: {problem}")
        print(
            "corpus: manifest verifies" if not problems else f"corpus: {len(problems)} problem(s)"
        )
        return 1 if problems else 0
    scoped = not args.no_scope and scope_available()
    failed = 0
    for outcome in run_corpus(root, scoped=scoped):
        code = outcome.result.returncode
        failed += code != 0
        extra = ""
        if outcome.scoped is not None:
            extra = f" processes={len(outcome.scoped.members)} leaked={len(outcome.scoped.leaked)}"
        print(
            f"corpus: {outcome.skill_id} [{outcome.label}] {outcome.run.script} exit={code}{extra}"
        )
    print(f"corpus: ran with{'' if scoped else 'out'} a cgroup scope per invocation")
    return 1 if failed else 0


def _roots(args: argparse.Namespace) -> list[Path]:
    roots: list[Path] = args.root or skill_roots()
    if not roots:
        raise SystemExit("skills: give --root or set CIM_SKILL_ROOTS")
    return roots


def _inventory(args: argparse.Namespace) -> int:
    found = take_inventory(_roots(args))
    with BaselineStore(args.db) as store:
        written = write_baselines(store, found, origin=args.origin)
        chain = store.verify_chain()
    print(
        f"inventory: skills={len(found)} new_baselines={len(written)} "
        f"chain={'ok' if chain.ok else 'broken'}"
    )
    return 0 if chain.ok else 1


def _print_sweep(result: SweepResult, quiet_when_unchanged: bool = False) -> None:
    for skill_id in result.new_skills:
        print(f"sweep: new skill {skill_id}", flush=True)
    for event in result.events:
        source = f" (was {event.old_path})" if event.old_path else ""
        print(f"sweep: {event.skill_id}: {event.change} {event.path}{source}", flush=True)
    if not quiet_when_unchanged and not result.new_skills and not result.events:
        print("sweep: unchanged", flush=True)


def _sweep(args: argparse.Namespace) -> int:
    with BaselineStore(args.db) as store:
        _print_sweep(sweep(store, _roots(args), origin=args.origin))
    return 0


def _watch(args: argparse.Namespace) -> int:
    roots = _roots(args)
    mode = "periodic sweep only" if args.no_inotify else "notifications + periodic sweep"
    print(f"watch: {len(roots)} root(s), every {args.interval:g}s, {mode}", flush=True)
    try:
        watch(
            args.db,
            roots,
            origin=args.origin,
            interval=args.interval,
            use_inotify=not args.no_inotify,
            report=lambda result: _print_sweep(result, quiet_when_unchanged=True),
        )
    except KeyboardInterrupt:
        pass
    return 0


def _observe(args: argparse.Namespace) -> int:
    if not scope_available():
        raise SystemExit("observe: needs a systemd user session (cgroup scope per invocation)")
    if not tracer_available():
        raise SystemExit("observe: needs strace, and permission to trace a child process")
    root: Path = args.corpus or default_root()
    manifest = load_manifest(root)
    skills = {skill.skill_id: skill for skill in discover_skills(root)}
    wanted = args.skill or sorted(manifest)
    unknown = [
        skill_id for skill_id in wanted if skill_id not in manifest or skill_id not in skills
    ]
    if unknown:
        raise SystemExit(f"observe: not in the corpus: {', '.join(unknown)}")
    with BaselineStore(args.db) as store:
        for skill_id in wanted:
            skill = skills[skill_id]
            for run in manifest[skill_id].runs:
                seen = observe(skill, skill.path / run.script, run.args)
                record_behaviour(store, skill, seen, origin=args.origin)
                events = ", ".join(f"{kind} {what}" for kind, what in seen.events) or "nothing"
                print(
                    f"observe: {skill_id} {run.script} exit={seen.run.result.returncode} "
                    f"processes={seen.process_count} leaked={len(seen.run.leaked)}: {events}",
                    flush=True,
                )
    return 0


def _envelope(args: argparse.Namespace) -> int:
    with BaselineStore(args.db) as store:
        found = profiles(store, args.skill)
    if not found:
        print("envelope: no behaviour records" + (f" for {args.skill}" if args.skill else ""))
        return 2
    for profile in found:
        print(profile.render())
    return 0


def _store_options(command: argparse.ArgumentParser) -> None:
    command.add_argument("--db", type=Path, required=True, help="baseline store path")
    command.add_argument(
        "--root",
        type=Path,
        action="append",
        help="skill root (repeatable; default: CIM_SKILL_ROOTS)",
    )
    command.add_argument(
        "--origin", default=DEFAULT_ORIGIN, help="host the skills are installed on"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cim.skills", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    corpus = commands.add_parser("corpus", help="verify, update or run the seed skill corpus")
    corpus.add_argument("action", choices=("verify", "update", "run"))
    corpus.add_argument("--root", type=Path, help="corpus directory (default: corpora/skills)")
    corpus.add_argument("--no-scope", action="store_true", help="run without cgroup scopes")
    corpus.set_defaults(handler=_corpus)
    inventory = commands.add_parser("inventory", help="store a baseline for every installed skill")
    _store_options(inventory)
    inventory.set_defaults(handler=_inventory)
    sweeper = commands.add_parser("sweep", help="record what changed since the stored baselines")
    _store_options(sweeper)
    sweeper.set_defaults(handler=_sweep)
    watcher = commands.add_parser("watch", help="record changes as they happen, until stopped")
    _store_options(watcher)
    watcher.add_argument(
        "--interval", type=float, default=DEFAULT_INTERVAL_S, help="seconds between sweeps"
    )
    watcher.add_argument(
        "--no-inotify", action="store_true", help="rely on the periodic sweep alone"
    )
    watcher.set_defaults(handler=_watch)
    observer = commands.add_parser(
        "observe", help="run corpus helpers under the collector and store what each one did"
    )
    observer.add_argument("--db", type=Path, required=True, help="baseline store path")
    observer.add_argument("--corpus", type=Path, help="corpus directory (default: corpora/skills)")
    observer.add_argument("--skill", action="append", help="skill id (repeatable; default: all)")
    observer.add_argument("--origin", default=DEFAULT_ORIGIN, help="host the skills run on")
    observer.set_defaults(handler=_observe)
    envelope = commands.add_parser(
        "envelope", help="show each skill's behavioural profile and whether warm-up is done"
    )
    envelope.add_argument("--db", type=Path, required=True, help="baseline store path")
    envelope.add_argument("--skill", help="one skill id (default: all)")
    envelope.set_defaults(handler=_envelope)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
