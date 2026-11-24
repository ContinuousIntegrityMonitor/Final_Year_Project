# PROJECT_STATUS — CIM (Layer-1 snapshot)

- **Updated:** 2026-11-24
- **Phase:** FYP I / Phase 1 (SEE) — target ~1 Dec 2026
- **Milestone:** December 2026 demo (C1–C6) — not yet fully achieved
- **Org `main`:** `fa869ce` — Fasih PRs [#20](https://github.com/ContinuousIntegrityMonitor/Final_Year_Project/pull/20)–[#26](https://github.com/ContinuousIntegrityMonitor/Final_Year_Project/pull/26) merged (after #16 T-16/T-16b)
- **Findings:** [`docs/HAMZA_REVIEW.md`](docs/HAMZA_REVIEW.md) · Report: [`docs/FASIH_MCP_TEST_REPORT.md`](docs/FASIH_MCP_TEST_REPORT.md) · Exchange: [`CONTEXT.md`](CONTEXT.md) · Log: [`ACTION.md`](ACTION.md)

## Remotes

| Remote | URL | Role |
|--------|-----|------|
| `origin` | https://github.com/HamzaFarooq3333/Final_Year_Project | Day-to-day + PR history |
| `org` | https://github.com/ContinuousIntegrityMonitor/Final_Year_Project | Committee / project home |

## Done on org `main` (selected)

| Task | Summary | Evidence |
|------|---------|----------|
| T-01 | Infra, CI, working agreement | early PRs |
| T-02 / T-04 / T-05 | Contract, MCP lab, skills runner skeleton | early PRs; **contract 1.1.0** = PR #26 |
| T-06–T-15 (skills + store/proxy/drift fixes) | Skills side + Fasih Stages 1–3 | PRs #2–#13 |
| Docs / dashboard research | Assistant exchange, research notes | PRs #9–#15 |
| T-16 / T-16b | Behaviour alerts + HTTP gateway; G1–G3 / X1–X2 | PR #16 |
| Fasih ask B/C | MCP test report + live stand-ins | PR #20 |
| U1 | Skills read model for the board | PR #21 |
| T-16 design | Shared scorer design note (docs only) | PR #22 |
| T-17 skills | Attacks A3/A4 corpus + runner | PR #23 |
| T-03 docs | Threat model v0.10; ADR-006 *Proposed* | PR #24 |
| T-13 design | Pipeline / CLI design note (docs only) | PR #25 |

## In flight / open decisions

| Item | Summary | Status |
|------|---------|--------|
| H1 gateway | Bearer attached with no gateway token | **Hamza fix next** (report High) |
| U1 wire-up | Dashboard uses `cim.skills.board` | Hamza (MCP/dashboard) |
| Shared scorer | Implement `common/scorer.py` | Waiting Hamza answers (design §11) |
| S2 / ADR-006 | Hash coverage formula | *Proposed* — both decide before code |
| T-13 | `cim.toml` + CLI reshape | Design on main — Hamza answers §10 |
| M2–M5 | SSE, session keys, Host on GET, failure records | Hamza territory after H1 |

## Next

**Hamza now:**
1. Fix **H1** (prefer refuse to start when `authorization_env` set and no gateway token).
2. Wire **U1** into the dashboard.
3. Answer scorer / S2 / T-13 decision lists in `CONTEXT.md` (or on the docs).
4. Adopt contract 1.1 MCP fields in the next proxy PR.

**Fasih:** wait for those answers before coding `common/scorer.py` or the T-13 CLI reshape.

## Decisions index

See [`DECISIONS.md`](DECISIONS.md). Agent skill names: [`docs/SKILLS_MANIFEST.txt`](docs/SKILLS_MANIFEST.txt).
