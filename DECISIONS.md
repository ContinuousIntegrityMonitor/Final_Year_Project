# DECISIONS — Continuous Integrity Monitor (CIM)

Single index of architecture and process decisions. Detailed write-ups live under `docs/decisions/`.

| ID | Title | Status | Date |
|----|--------|--------|------|
| ADR-001 | Tooling (Python 3.12, uv, ruff, mypy, pytest, dual CI) | Accepted | 2026-10-03 |
| ADR-002 | Dual GitHub remotes (personal + org project repo) | Accepted | 2026-11-07 |
| ADR-003 | FYP I Dec scope (functional SEE path; product polish = FYP II) | Accepted | 2026-11-07 |

## Working rules (stable)

- Territory: `src/cim/mcp/` = Hamza; `src/cim/skills/` = Fasih; `common/` = joint (PR + both review).
- Branches: `tXX-slug`; PR titles: `T-XX: …`; no force-push to `main`.
- No AI tool as author, committer, or co-author on any commit. Enforced by `scripts/check_ai_coauthor.py` in ci-push and merge-gate (full history) and by `tests/common/test_no_ai_coauthor.py`.
- Progress truth: `progress/tasks/T-XX.md`; history: `history/entries/`.
- Agent skills for this workspace: copied under `.agents/skills/` (gitignored bodies); names listed in `docs/SKILLS_MANIFEST.txt`.
