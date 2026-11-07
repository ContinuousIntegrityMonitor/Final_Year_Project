# CONTEXT — CIM onboarding

1. **What:** Continuous Integrity Monitor — detect MCP rug-pulls / trigger tools and skills-side integrity + behavioural drift on a monitored host. Demo host: lab VM-MON. HexStrike pin: `corpora/mcp/hexstrike.pin` (`d689933ff579d839c676c82b231f8e98326c5f04`).
2. **Phase:** Phase 1 (SEE). Next milestone: December 2026 working demo (C1–C6).
3. **Active now:** T-04 MCP lab recorded in-repo (H). Next joint task: T-06 baseline store (impl H, review F). Fasih continues T-05.
4. **Territory:** `src/cim/mcp/` = Hamza; `src/cim/skills/` = Fasih; border = `common/`, `history/`, `progress/`, `scripts/`, root. Full map: DIRECTORY.md; rules: `docs/plan/Final_Year_Project_Latest.pdf`.
5. **Rules R1–R6:** one monorepo; sole territories; border PR-only + both review; protected `main`; full suite green; generated files regenerated never hand-edited.
6. **Git:** branches `tXX-slug`; PR titles `T-XX: description`; AI never commits/pushes/merges.
7. **Division of truth:** `progress/` = status; `history/` = interpretation; GitHub = raw events; this file = orientation.
8. **AI layers:** L1 GitHub reviewer (advisory); L2 history drafts (author verifies); L3 progress drafts (both verify).

Paste into any AI session: *You are assisting with CIM. Read CONTEXT.md and DIRECTORY.md first, then the plan PDF. Follow the territory map and PR rules; never commit or push; attribute every draft; stop and ask when a rule is unclear.*
