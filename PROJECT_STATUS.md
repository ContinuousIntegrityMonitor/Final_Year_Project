# PROJECT_STATUS — CIM (Layer-1 snapshot)

- **Updated:** 2026-11-09
- **Phase:** FYP I / Phase 1 (SEE) — target ~1 Dec 2026
- **Milestone:** December 2026 demo (C1–C6) — not yet achieved
- **Local tests:** `uv run pytest -q` passed on 2026-11-09 (Windows, project venv on D:)
- **Fasih review queue:** [`docs/FASIH_REVIEW.md`](docs/FASIH_REVIEW.md) — no reply yet

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
| T-06 | Baseline store (SQLite WAL + hash chain) | Org PR [#1](https://github.com/ContinuousIntegrityMonitor/Final_Year_Project/pull/1) — **awaiting Fasih** (no review yet) |
| T-07 | MCP artefact inventory | Org branch `t07-mcp-inventory` (`15811b0`), stacked on T-06 |
| T-09 | MCP proxy collector v1 (critical path, C2) | Org branch `t09-mcp-proxy` (`048acce`); a tool call on VM-MON is still open |
| T-12 | Rug-pull detector | Org branch `t12-mcp-drift` (`2bf8c42`); live sweep open |
| T-14 | MCP behavioural envelope | Org branch `t14-mcp-envelope` (`91e52bb`); scoring is T-16 |
| Status board | `cim dashboard` home page | Branch `t14-status-board`. Counts only; the list is behind "See the list". Activity lines appear when a tool is used |

## Next (MCP / Hamza)

1. Fasih reviews T-06 once on org PR #1 and replies ok or with the changes he wants. He has not reviewed yet. Work continues meanwhile.
2. Pinned HexStrike `d689933` is checked out on this PC. `tools/list` (150 tools) is in `corpora/mcp/tools_list.json` and in a local store. A tool call, and the same session on VM-MON, are still open. No scan was run.
3. T-16 behaviour alert is the next thing to build. The MCP half can start from the call pattern. The skills half waits on Fasih.

## Decisions index

See [`DECISIONS.md`](DECISIONS.md). Agent skill names: [`docs/SKILLS_MANIFEST.txt`](docs/SKILLS_MANIFEST.txt).
