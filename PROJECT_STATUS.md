# PROJECT_STATUS — CIM (Layer-1 snapshot)

- **Updated:** 2026-11-25
- **Phase:** FYP I / Phase 1 (SEE) — target week of **14 Dec 2026** (plan §2.1); older “~1 Dec” notes are stale
- **Milestone:** December 2026 demo (C1–C6) — not yet fully achieved live (see `progress/milestones/dec-demo-2026.md`)
- **Org `main`:** after **#49** (score by record id / outcome A1); tip @ `7c0bc6f`
- **Findings:** [`docs/HAMZA_REVIEW.md`](docs/HAMZA_REVIEW.md) · Report: [`docs/FASIH_MCP_TEST_REPORT.md`](docs/FASIH_MCP_TEST_REPORT.md) · Exchange: [`CONTEXT.md`](CONTEXT.md) · Log: [`ACTION.md`](ACTION.md) · Handover: [`docs/HAMZA_HANDOVER.md`](docs/HAMZA_HANDOVER.md)

## Remotes

| Remote | URL | Role |
|--------|-----|------|
| `origin` | https://github.com/HamzaFarooq3333/Final_Year_Project | Day-to-day + PR history |
| `org` | https://github.com/ContinuousIntegrityMonitor/Final_Year_Project | Committee / project home |

## Done on org `main` (selected)

| Task | Summary | Evidence |
|------|---------|----------|
| T-07 / T-09 / T-12 / T-14 | Inventory, proxy, drift, envelope on `main` | merges since 2026-11-09 |
| T-16 / T-16b | Behaviour alerts + HTTP gateway; G1–G3 / X1–X2 | PR #16 |
| Fasih ask stack | Report, U1, designs, T-17, contract 1.1 schema | PRs #20–#26 |
| H1 + U1 UI | Gateway token required; Skills + MCP panels | PR #28 |
| Status / ADR-007 / milestone / digests / skills exec | | PRs #29–#33 |
| Green light §11 / §10 | Scorer + T-13 answers | PR #34 + issue #19 |
| Contract 1.1 MCP writers | Chained behaviour / session / pin / detail / tool_digest | PR #35 |
| Windows ship gates | `prepush_local` `--help` recursion + posix skill paths | PR #36 |
| MCP score_latest on chain | Observations from behaviour records; not `envelope_obs` (M1) | PR #37 |
| M2 / M3 / M5 / L1 | SSE stream, session Capture, Host on GET, `%2e%2e` refuse | PR #39 |
| ADR-006 hash v2 | `store_meta.hash_version=2`; ts + artefact in hash; v1 refuse-append | PR #40 |
| Shared scorer | `cim.common.scorer` milli-z + A1 baseline | PR #42 |
| MCP scorer wire | `score_latest` → shared library + BehaviourAlertPayload | PR #43 |
| Fasih review #42/#43 | Findings in CONTEXT (score-by-id bug, outcome A1) | PR #45 |
| Skills behaviour alerts | `skill_behaviour_drift` via shared scorer | PR #46 |
| Threshold sweep | `scorer_sweep.py` + recorded results | PR #47 |

## Decisions (Hamza)

| Item | Status |
|------|--------|
| Scorer §11 | **Done** library + MCP + skills wire (#42/#43/#46) |
| T-13 §10 (+ decision 8) | **Green light** — Fasih implements shared; Hamza does (7) after |
| Finding 1 (score by record id) | **Done** (#49) |
| Finding 2 (outcome joins window) | **Done** (#49) |
| ADR-006 hash formula | **Done** (#40) |
| H2 live scripts | Keep Fasih stand-ins |
| Demo date | Prefer plan: week of **14 Dec 2026** |

## Open / next

| Item | Owner | Status |
|------|-------|--------|
| MCP findings 1–2 | Hamza | **Done** (#49) |
| T-13 shared CLI / `cim status` | Fasih | In progress (announced) |
| T-13 decision‑7 MCP pieces | Hamza | After Fasih structure |
| Live MCP + skills demo | Both | After finding 1 |
| T-17 MCP attack pack A1/A2 | Hamza | Open |
| C6 video / demo script | Both | Open |
| FYP I progress (rough) | — | ~80% code; ~55–60% live C1–C6 |

## Decisions index

See [`DECISIONS.md`](DECISIONS.md). Agent skill names: [`docs/SKILLS_MANIFEST.txt`](docs/SKILLS_MANIFEST.txt).
