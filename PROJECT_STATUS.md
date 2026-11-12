# PROJECT_STATUS — CIM (Layer-1 snapshot)

- **Updated:** 2026-11-12
- **Phase:** FYP I / Phase 1 (SEE) — target ~1 Dec 2026
- **Milestone:** December 2026 demo (C1–C6) — not yet achieved
- **Local tests:** `uv run pytest -q` passed on 2026-11-09 (Windows, project venv on D:)
- **Fasih review queue:** [`docs/FASIH_REVIEW.md`](docs/FASIH_REVIEW.md) — no reply yet

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
| T-16 | Behaviour alerts | MCP half in progress: live path = Cursor Playwright through `cim proxy` (`docs/setup/cursor-playwright-cim.md`). Skills half waits on Fasih. |
| T-16b | HTTP MCP gateway | **Code landed 2026-11-12** (`cim http-gateway`). Live warm-up + OAuth env tokens still open. How-to: `docs/setup/cursor-http-mcp-gateway.md`. |

## Next (MCP / Hamza)

1. Reload Cursor MCP for Playwright; run dashboard on `logs/cursor-playwright.sqlite`; warm-up 30+ calls; show one live behaviour alert (C4 step).
2. Start `cim http-gateway`; reload URL MCPs; prove one URL server on `logs/cursor-http.sqlite` (Graphiti first if local).
3. VM-MON: one HexStrike session through `cim proxy` (graded lab).
4. Fasih: skills envelope / skills half of T-16 / T-13 `cim status` when he pushes.

## Decisions index

See [`DECISIONS.md`](DECISIONS.md). Agent skill names: [`docs/SKILLS_MANIFEST.txt`](docs/SKILLS_MANIFEST.txt).
