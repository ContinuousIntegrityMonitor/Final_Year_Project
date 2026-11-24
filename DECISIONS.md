# DECISIONS — Continuous Integrity Monitor (CIM)

Single index of architecture and process decisions. Detailed write-ups live under `docs/decisions/`.

| ID | Title | Status | Date |
|----|--------|--------|------|
| ADR-001 | Tooling (Python 3.12, uv, ruff, mypy, pytest, dual CI) | Accepted | 2026-10-03 |
| ADR-002 | Dual GitHub remotes (personal + org project repo) | Accepted | 2026-11-07 |
| ADR-003 | FYP I Dec scope (functional SEE path; product polish = FYP II) | Accepted | 2026-11-07 |
| ADR-004 | MCP proxy fails open in v1 (forward everything; alert on unparseable frames) | Accepted | 2026-11-08 |
| ADR-005 | Stdio proxy and HTTP MCP gateway (both transports) | Accepted | 2026-11-12 |
| ADR-006 | What the record hash covers: `ts`, `artefact_id` and the artefact row, with a version tag (S2) | Accepted (implement later) | 2026-11-24 |
| ADR-007 | Skills helper / monitor boundary (T-11): one user and a precise claim for FYP I; monitor and store as their own user for FYP II | Accepted (skills side; T-13 decision 8 pending) | 2026-11-24 |

## Working rules (stable)

- Territory: `src/cim/mcp/` = Hamza; `src/cim/skills/` = Fasih; `common/` = joint (PR + both review).
- Branches: `tXX-slug`; PR titles: `T-XX: …`; no force-push to `main`.
- No AI tool as author, committer, or co-author on any commit. Enforced by `scripts/check_ai_coauthor.py` in ci-push and merge-gate (full history) and by `tests/common/test_no_ai_coauthor.py`.
- Progress truth: `progress/tasks/T-XX.md`; history: `history/entries/`.
- Agent skills for this workspace: copied under `.agents/skills/` (gitignored bodies); names listed in `docs/SKILLS_MANIFEST.txt`.
- Joint review queue for Fasih / Claude: [`docs/FASIH_REVIEW.md`](docs/FASIH_REVIEW.md).
- Do not merge T-06 until Fasih approves; Hamza stacks T-07 and T-09 on the T-06 branch meanwhile.
- Schema changes in `src/cim/common/schema/` need both members; Hamza files requests in `docs/FASIH_REVIEW.md` instead of editing alone.
