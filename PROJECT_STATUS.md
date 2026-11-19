# PROJECT_STATUS — CIM (Layer-1 snapshot)

- **Updated:** 2026-11-19
- **Phase:** FYP I / Phase 1 (SEE) — target ~1 Dec 2026
- **Milestone:** December 2026 demo (C1–C6) — not yet fully achieved
- **Org `main`:** `e27f6dd` — PR [#16](https://github.com/ContinuousIntegrityMonitor/Final_Year_Project/pull/16) merged (T-16 + T-16b + G1–G3 / X1–X2)
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
| T-16 / T-16b | Behaviour alerts + HTTP gateway; G1–G3 / X1–X2 | PR #16 → `main` @ `e27f6dd` |

## In flight (not on `main` yet)

| Task | Summary | Status |
|------|---------|--------|
| T-03 | Threat model draft | branch `t03-threat-model` |
| Contract fixes | B1–B3 + v1.1 answers | Fasih local `t02-contract-fixes` |

## Next (MCP / Hamza)

1. OAuth URL wrap for gateway (`CIM_MCP_AUTH_*`) — operator.
2. S2 hash decision + U1 skills board shape — wait on Fasih proposals.
3. VM-MON HexStrike through `cim proxy` when scheduled.
4. Skills half of T-16 / shared scorer (A2) — Fasih.
5. Optional: delete superseded `t16-alerts-http-dashboard` on org.

## Decisions index

See [`DECISIONS.md`](DECISIONS.md). Agent skill names: [`docs/SKILLS_MANIFEST.txt`](docs/SKILLS_MANIFEST.txt).
