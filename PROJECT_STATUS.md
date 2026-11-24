# PROJECT_STATUS — CIM (Layer-1 snapshot)

- **Updated:** 2026-11-24
- **Phase:** FYP I / Phase 1 (SEE) — target week of **14 Dec 2026** (plan §2.1); older “~1 Dec” notes are stale
- **Milestone:** December 2026 demo (C1–C6) — not yet fully achieved live (see `progress/milestones/dec-demo-2026.md`)
- **Org `main`:** after **#39** (M2/M3/M5/L1); tip @ `c5f1ac3`; ADR-006 hash v2 shipping next
- **Findings:** [`docs/HAMZA_REVIEW.md`](docs/HAMZA_REVIEW.md) · Report: [`docs/FASIH_MCP_TEST_REPORT.md`](docs/FASIH_MCP_TEST_REPORT.md) · Exchange: [`CONTEXT.md`](CONTEXT.md) · Log: [`ACTION.md`](ACTION.md)

## Remotes

| Remote | URL | Role |
|--------|-----|------|
| `origin` | https://github.com/HamzaFarooq3333/Final_Year_Project | Day-to-day + PR history |
| `org` | https://github.com/ContinuousIntegrityMonitor/Final_Year_Project | Committee / project home |

## Done on org `main` (selected)

| Task | Summary | Evidence |
|------|---------|----------|
| T-07 / T-09 / T-12 / T-14 | Inventory, proxy, drift, envelope on `main` | merges since 2026-11-09; task files refreshed |
| T-16 / T-16b | Behaviour alerts + HTTP gateway; G1–G3 / X1–X2 | PR #16 |
| Fasih ask stack | Report, U1, designs, T-17, contract 1.1 schema | PRs #20–#26 |
| H1 + U1 UI | Gateway token required; Skills + MCP panels | PR #28 |
| Status / ADR-007 / milestone / digests / skills exec | | PRs #29–#33 |
| Green light §11 / §10 | Scorer + T-13 answers | PR #34 + issue #19 |
| Contract 1.1 MCP writers | Chained behaviour / session / pin / detail / tool_digest | PR #35 |
| Windows ship gates | `prepush_local` `--help` recursion + posix skill paths | PR #36 |
| MCP score_latest on chain | Observations from behaviour records; not `envelope_obs` (M1) | PR #37 |
| M2 / M3 / M5 / L1 | SSE stream, session Capture, Host on GET, `%2e%2e` refuse | PR #39 |

## Decisions (Hamza)

| Item | Status |
|------|--------|
| Scorer §11 | **Green light** — `CONTEXT.md` |
| T-13 §10 (+ decision 8) | **Green light** — `CONTEXT.md` |
| ADR-006 hash formula | Accepted; **code shipping** (hash v2) |
| H2 live scripts | Keep Fasih stand-ins |
| Demo date | Prefer plan: week of **14 Dec 2026** |

## Open / next

| Item | Owner | Status |
|------|-------|--------|
| ADR-006 store hash v2 | Hamza | Shipping |
| MCP `score_latest` → shared `common/scorer.py` | Hamza | After Fasih library lands |
| `common/scorer.py` + skills alerts | Fasih | Unblocked |
| T-13 pipeline / `cim status` | Fasih (+ Hamza MCP pieces) | Unblocked |
| M2–M5 / L1 | Hamza | Done (#39) |

## Decisions index

See [`DECISIONS.md`](DECISIONS.md). Agent skill names: [`docs/SKILLS_MANIFEST.txt`](docs/SKILLS_MANIFEST.txt).
