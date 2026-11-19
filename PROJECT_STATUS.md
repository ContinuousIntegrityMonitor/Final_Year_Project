# PROJECT_STATUS — CIM (Layer-1 snapshot)

- **Updated:** 2026-11-19
- **Phase:** FYP I / Phase 1 (SEE) — target ~1 Dec 2026
- **Milestone:** December 2026 demo (C1–C6) — not yet fully achieved
- **Org PR open:** [#16](https://github.com/ContinuousIntegrityMonitor/Final_Year_Project/pull/16) — T-16 + T-16b + G1–G3 / X1–X2 (CI green; awaiting Hamza merge)
- **Findings:** [`docs/HAMZA_REVIEW.md`](docs/HAMZA_REVIEW.md) · Exchange: [`CONTEXT.md`](CONTEXT.md) · Log: [`ACTION.md`](ACTION.md)

## Remotes

| Remote | URL | Role |
|--------|-----|------|
| `origin` | https://github.com/HamzaFarooq3333/Final_Year_Project | Day-to-day + PR history |
| `org` | https://github.com/ContinuousIntegrityMonitor/Final_Year_Project | Committee / project home |

## Done on org `main` (selected)

| Task | Summary | Evidence |
|------|---------|----------|
| T-01 | Infra, CI, working agreement | early PRs |
| T-02 / T-04 / T-05 | Contract, MCP lab, skills runner skeleton | early PRs |
| T-06–T-15 (skills + store/proxy/drift fixes) | Skills side + Fasih Stages 1–3 | PRs #2–#13, #10 exchange |
| Docs / dashboard research | Assistant exchange, research notes | PRs #9–#15 |

## In flight (not on `main` yet)

| Task | Summary | Status |
|------|---------|--------|
| T-16 | MCP behaviour alerts (`score_latest` after warm-up) | PR #16 branch `t16-alerts-on-main` — CI green |
| T-16b | HTTP / Streamable-HTTP MCP gateway | Same PR #16; G1–G3 hardened |
| Dashboard demo path | `--demo` + token; unusual → real scorer (X1/X2) | Same PR #16 |
| T-03 | Threat model draft | branch `t03-threat-model` |
| Contract fixes | B1–B3 + v1.1 answers | Fasih local `t02-contract-fixes` |

## Next (MCP / Hamza)

1. Merge PR #16 when ready; sync local mirrors (`fresh/main`).
2. OAuth URL wrap for gateway (`CIM_MCP_AUTH_*`) — operator.
3. S2 hash decision + U1 skills board shape — wait on Fasih proposals.
4. VM-MON HexStrike through `cim proxy` when scheduled.
5. Skills half of T-16 / shared scorer (A2) — Fasih.

## Decisions index

See [`DECISIONS.md`](DECISIONS.md). Agent skill names: [`docs/SKILLS_MANIFEST.txt`](docs/SKILLS_MANIFEST.txt).
