# PROJECT_STATUS — CIM (Layer-1 snapshot)

- **Updated:** 2026-11-24
- **Phase:** FYP I / Phase 1 (SEE) — target ~1 Dec 2026 (plan also cites week of 14 Dec; align with Fasih)
- **Milestone:** December 2026 demo (C1–C6) — not yet fully achieved live
- **Org `main`:** after Fasih **#29–#33**; H1+U1 already on main (#28)
- **Findings:** [`docs/HAMZA_REVIEW.md`](docs/HAMZA_REVIEW.md) · Report: [`docs/FASIH_MCP_TEST_REPORT.md`](docs/FASIH_MCP_TEST_REPORT.md) · Exchange: [`CONTEXT.md`](CONTEXT.md) · Log: [`ACTION.md`](ACTION.md)

## Remotes

| Remote | URL | Role |
|--------|-----|------|
| `origin` | https://github.com/HamzaFarooq3333/Final_Year_Project | Day-to-day + PR history |
| `org` | https://github.com/ContinuousIntegrityMonitor/Final_Year_Project | Committee / project home |

## Done on org `main` (selected)

| Task | Summary | Evidence |
|------|---------|----------|
| T-16 / T-16b | Behaviour alerts + HTTP gateway; G1–G3 / X1–X2 | PR #16 |
| Fasih ask stack | Report, U1, designs, T-17, contract 1.1 | PRs #20–#26 |
| H1 + U1 UI | Gateway token required; Skills + MCP panels | PR #28 |
| Status / ADR-007 / milestone / digests / skills exec | After H1 check; boundary ADR; C1–C6 rewrite; digest fix; `cim.skills exec` | PRs #29–#33 |

## Decisions (Hamza, 2026-11-24)

| Item | Status |
|------|--------|
| Scorer §11 | **Green light** — see `CONTEXT.md` Hamza section |
| T-13 §10 (+ decision 8) | **Green light** — see `CONTEXT.md` Hamza section |
| ADR-006 hash formula | Accepted; **code** still open |
| H2 live scripts | Keep Fasih stand-ins |

## Open / next

| Item | Owner | Status |
|------|-------|--------|
| Contract 1.1 MCP writers (M1 off-chain) | Hamza | Next implement |
| MCP `score_latest` → shared scorer | Hamza | After writers + Fasih library |
| `common/scorer.py` + skills alerts | Fasih | Unblocked |
| T-13 pipeline / `cim status` | Fasih (+ Hamza MCP pieces) | Unblocked |
| ADR-006 store formula code | Hamza | After writers |
| M2–M5 / L1 | Hamza | After writers / scorer path |

## Decisions index

See [`DECISIONS.md`](DECISIONS.md). Agent skill names: [`docs/SKILLS_MANIFEST.txt`](docs/SKILLS_MANIFEST.txt).
