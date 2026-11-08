# PROJECT_STATUS — CIM (Layer-1 snapshot)

- **Updated:** 2026-11-08
- **Phase:** FYP I / Phase 1 (SEE) — target ~1 Dec 2026
- **Milestone:** December 2026 demo (C1–C6) — not yet achieved
- **Fasih review queue:** [`docs/FASIH_REVIEW.md`](docs/FASIH_REVIEW.md)

## Remotes

| Remote | URL | Role |
|--------|-----|------|
| `origin` | https://github.com/HamzaFarooq3333/Final_Year_Project | Day-to-day + PR history |
| `org` | https://github.com/ContinuousIntegrityMonitor/Final_Year_Project | Committee / project home |

## Done on `main`

| Task | Summary | Evidence |
|------|---------|----------|
| T-01 | Infra, CI, working agreement | PR #1 (+ follow-ups) |
| T-05 | Skills runner skeleton | PR #6 |
| T-02 | Event / data contract v1.0 | PR #8 |
| T-04 | MCP lab (HexStrike pin, topology, stdio spike) | PR #162 |

## In flight

| Task | Summary | Status |
|------|---------|--------|
| T-06 | Baseline store (SQLite WAL + hash chain) | PR #163 — **awaiting Fasih** (joint) |
| T-07 | MCP artefact inventory | Branch `t07-mcp-inventory`, stacked on T-06 (Hamza sole) |
| T-09 | MCP proxy collector v1 (critical path, C2) | Branch `t09-mcp-proxy`, stacked on T-07; lab run vs HexStrike open |
| T-12 | Rug-pull detector | Branch `t12-mcp-drift`, stacked on T-09 |
| T-14 | MCP behavioural envelope | Branch `t14-mcp-envelope`, stacked on T-12; scoring is T-16 |

## Next (MCP / Hamza)

1. Fasih reviews T-06 once (`docs/FASIH_REVIEW.md`) and says whether the store needs changes. Work continues meanwhile.
2. Lab: capture HexStrike `tools/list` and run a session through `cim proxy` on VM-MON (C1/C2 evidence)
3. T-16 drift scorer once Fasih's skills envelope exists

## Decisions index

See [`DECISIONS.md`](DECISIONS.md). Agent skill names: [`docs/SKILLS_MANIFEST.txt`](docs/SKILLS_MANIFEST.txt).
