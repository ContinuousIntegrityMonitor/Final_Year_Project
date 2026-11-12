# PROJECT_STATUS — CIM (Layer-1 snapshot)

- **Updated:** 2026-11-12
- **Phase:** FYP I / Phase 1 (SEE) — target ~1 Dec 2026
- **Milestone:** December 2026 demo (C1–C6) — not yet achieved
- **Local tests:** `uv run pytest -q` passed on 2026-11-09 (Windows, project venv on D:)
- **Fasih review queue:** [`docs/FASIH_REVIEW.md`](docs/FASIH_REVIEW.md) — no reply yet
- **Fasih dashboard research:** [`docs/FASIH_DASHBOARD_RESEARCH.md`](docs/FASIH_DASHBOARD_RESEARCH.md) — form factor, sections, auto-disconnect (research only)

## Remotes

| Remote | URL | Role |
|--------|-----|------|
| `origin` | https://github.com/HamzaFarooq3333/Final_Year_Project | Day-to-day + PR history |
| `org` | https://github.com/ContinuousIntegrityMonitor/Final_Year_Project | Committee / project home |

## Done on `main` / org shipped line

| Task | Summary | Evidence |
|------|---------|----------|
| T-01 | Infra, CI, working agreement | Org rebuild line |
| T-05 | Skills runner skeleton | PR #6 |
| T-02 | Event / data contract v1.0 | PR #8 |
| T-04 | MCP lab (HexStrike pin, topology, stdio spike) | PR #162 |
| T-06 | Baseline store (SQLite WAL + hash chain) | On org main |
| T-07 | MCP artefact inventory | Org / status board line |
| T-09 | MCP proxy collector v1 | Org; Cursor Playwright wrap 2026-11-12 |
| T-12 | Rug-pull detector | Org |
| T-14 | MCP behavioural envelope | Org |
| Status board | `cim dashboard` | Org + local demo UI |

## In flight

| Task | Summary | Status |
|------|---------|--------|
| T-16 | Behaviour alerts | MCP half **live done** 12 Nov 2026 (Playwright + HTTP demo). Skills half waits on Fasih. |
| T-16b | HTTP MCP gateway | **Code + live warm-up done** 12 Nov 2026. OAuth `CIM_MCP_AUTH_*` wrap still optional. How-to: `docs/setup/cursor-http-mcp-gateway.md`. |
| Dashboard product | Final UI research (Fasih) | Brief filed 12 Nov 2026. Current board stays demo-only until research lands. |

## Next (MCP / Hamza)

1. VM-MON: one HexStrike session through `cim proxy` (graded lab).
2. Optional: OAuth URL MCPs via gateway (`CIM_MCP_AUTH_*`).
3. Fasih: skills envelope / T-16 skills half / T-13 `cim status`, plus dashboard research in `docs/FASIH_DASHBOARD_RESEARCH.md`.

## Decisions index

See [`DECISIONS.md`](DECISIONS.md). Agent skill names: [`docs/SKILLS_MANIFEST.txt`](docs/SKILLS_MANIFEST.txt).
