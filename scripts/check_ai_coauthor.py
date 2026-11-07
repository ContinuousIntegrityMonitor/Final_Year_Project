"""Fail if any commit credits an AI tool as author, committer, or co-author.

Project rule: commits are authored by team members only. Run over the full
history in CI (checkout needs fetch-depth: 0).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass

AI_IDENTITY = re.compile(r"cursor|cursoragent|copilot|claude|openai|chatgpt", re.IGNORECASE)
TRAILER = re.compile(r"^\s*co-authored-by:\s*(?P<who>.+)$", re.IGNORECASE | re.MULTILINE)
FIELD_SEP = "\x1f"
RECORD_SEP = "\x1e"
LOG_FORMAT = FIELD_SEP.join(["%H", "%an", "%ae", "%cn", "%ce", "%B"]) + RECORD_SEP


@dataclass(frozen=True)
class Violation:
    sha: str
    reason: str


def find_violations(log_text: str) -> list[Violation]:
    """Parse `git log --format=LOG_FORMAT` output and return offending commits."""
    found: list[Violation] = []
    for record in log_text.split(RECORD_SEP):
        record = record.strip("\n")
        if not record:
            continue
        sha, author, author_email, committer, committer_email, body = record.split(FIELD_SEP, 5)
        people = {
            "author": f"{author} <{author_email}>",
            "committer": f"{committer} <{committer_email}>",
        }
        for role, ident in people.items():
            if AI_IDENTITY.search(ident):
                found.append(Violation(sha, f"{role} is an AI identity: {ident}"))
        for match in TRAILER.finditer(body):
            who = match.group("who").strip()
            if AI_IDENTITY.search(who):
                found.append(Violation(sha, f"AI co-author trailer: {who}"))
    return found


def git_log(rev: str) -> str:
    return subprocess.run(
        ["git", "log", f"--format={LOG_FORMAT}", rev],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rev", default="HEAD", help="revision or range to scan (default HEAD)")
    args = parser.parse_args(argv)
    violations = find_violations(git_log(args.rev))
    for v in violations:
        print(f"{v.sha[:12]} {v.reason}")
    if violations:
        print(f"FAIL: {len(violations)} commit(s) credit an AI tool", file=sys.stderr)
        return 1
    print("OK: no AI authors or co-authors in history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
