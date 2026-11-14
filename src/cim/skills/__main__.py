"""Skills-side commands: python -m cim.skills <command>.

These stay here, not in the shared `cim` CLI, until pipeline integration (T-13).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cim.skills.corpus import default_root, run_corpus, update_manifest, verify_manifest
from cim.skills.scoped import scope_available


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cim.skills", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    corpus = commands.add_parser("corpus", help="verify, update or run the seed skill corpus")
    corpus.add_argument("action", choices=("verify", "update", "run"))
    corpus.add_argument("--root", type=Path, help="corpus directory (default: corpora/skills)")
    corpus.add_argument("--no-scope", action="store_true", help="run without cgroup scopes")
    corpus.set_defaults(handler=_corpus)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
