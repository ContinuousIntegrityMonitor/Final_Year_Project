# CONTEXT — CIM onboarding

1. **What:** Continuous Integrity Monitor — detect MCP rug-pulls / trigger tools and skills-side integrity + behavioural drift on a monitored host. Demo host: lab VM-MON. HexStrike pin: `corpora/mcp/hexstrike.pin` (`d689933ff579d839c676c82b231f8e98326c5f04`).
2. **Phase:** Phase 1 (SEE) / FYP I. Milestone: December 2026 demo (C1–C6). Scope: ADR-003.
3. **Active now:** T-04 Done (PR #162). T-06 baseline store on org PR #1 (impl H, **awaiting Fasih review** — no reply yet; do not merge without it). T-07, T-09, T-12, and T-14 are on the org remote. `t14-status-board` adds the dashboard and a float-safe record of the pinned HexStrike tool list (150 tools, captured on the dev PC; VM-MON call still open). Next build is T-16. Dual remotes `origin` + `org` (ADR-002). Joint review checklist: [`docs/FASIH_REVIEW.md`](docs/FASIH_REVIEW.md).
4. **Territory:** `src/cim/mcp/` = Hamza; `src/cim/skills/` = Fasih; border = `common/`, `history/`, `progress/`, `scripts/`, root. Full map: DIRECTORY.md; rules: `docs/plan/Final_Year_Project_Latest.pdf`.
5. **Rules R1–R6:** one monorepo; sole territories; border PR-only + both review; protected `main`; full suite green; generated files regenerated never hand-edited.
6. **Git:** branches `tXX-slug`; PR titles `T-XX: description`; no Cursor/AI co-author trailers; push accepted phases to **both** remotes.
7. **Division of truth:** `progress/` = status; `history/` = interpretation; GitHub = raw events; `DECISIONS.md` / `PROJECT_STATUS.md` = Layer-1 memory; this file = orientation.
8. **AI layers:** L1 GitHub reviewer (advisory); L2 history drafts (author verifies); L3 progress drafts (both verify). Skills bodies under `.agents/skills/` (gitignored); names in `docs/SKILLS_MANIFEST.txt`.

Paste into any AI session: *You are assisting with CIM. Read CONTEXT.md, PROJECT_STATUS.md, DECISIONS.md, docs/FASIH_REVIEW.md, and DIRECTORY.md first, then the plan PDF. Follow the territory map and PR rules; no AI co-author trailers; stop and ask when a rule is unclear.*
