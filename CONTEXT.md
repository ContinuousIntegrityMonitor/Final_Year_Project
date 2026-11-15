# CONTEXT — CIM onboarding

1. **What:** Continuous Integrity Monitor — detect MCP rug-pulls / trigger tools and skills-side integrity + behavioural drift on a monitored host. Demo host: lab VM-MON. HexStrike pin: `corpora/mcp/hexstrike.pin` (`d689933ff579d839c676c82b231f8e98326c5f04`).
2. **Phase:** Phase 1 (SEE) / FYP I. Milestone: December 2026 demo (C1–C6). Scope: ADR-003.
3. **Active now (2026-11-15):** On org `main`: MCP side T-06 store, T-07, T-09, T-12, T-14 and the status board; skills side T-05 (runner, cgroup scope, seed corpus), T-08, T-10, T-11 and the T-15 profile (org PRs #2 and #4 to #8). Also on `main`: review notes `docs/HAMZA_REVIEW.md` (PR #3) and dashboard research notes (PR #9). Not on `main`: `t16-alerts-http-dashboard` (T-16 MCP alerts, HTTP gateway), `t03-threat-model` (draft), and three contract fixes that are still local to Fasih. Nothing has run on VM-MON. Open findings are listed in `docs/HAMZA_REVIEW.md`. Dual remotes `origin` + `org` (ADR-002). Joint review checklist: [`docs/FASIH_REVIEW.md`](docs/FASIH_REVIEW.md). Who did what, day by day: [`ACTION.md`](ACTION.md).
4. **Territory:** `src/cim/mcp/` = Hamza; `src/cim/skills/` = Fasih; border = `common/`, `history/`, `progress/`, `scripts/`, root. Full map: DIRECTORY.md; rules: `docs/plan/Final_Year_Project_Latest.pdf`.
5. **Rules R1–R6:** one monorepo; sole territories; border PR-only + both review; protected `main`; full suite green; generated files regenerated never hand-edited.
6. **Git:** branches `tXX-slug`; PR titles `T-XX: description`; no Cursor/AI co-author trailers; push accepted phases to **both** remotes.
7. **Division of truth:** `progress/` = status; `history/` = interpretation; GitHub = raw events; `DECISIONS.md` / `PROJECT_STATUS.md` = Layer-1 memory; this file = orientation.
8. **AI layers:** L1 GitHub reviewer (advisory); L2 history drafts (author verifies); L3 progress drafts (both verify). Skills bodies under `.agents/skills/` (gitignored); names in `docs/SKILLS_MANIFEST.txt`.

Paste into any AI session: *You are assisting with CIM. Read CONTEXT.md (including the assistant exchange at the end), ACTION.md, PROJECT_STATUS.md, DECISIONS.md, docs/FASIH_REVIEW.md, docs/HAMZA_REVIEW.md and DIRECTORY.md first, then the plan PDF. Follow the territory map and PR rules; no AI co-author trailers; stop and ask when a rule is unclear.*

---

## Assistant exchange

Fasih and Hamza each work with an AI assistant. This section is how the two assistants tell each other what they did and what they need. It is not a status board (that is `PROJECT_STATUS.md`) and not a log (that is `ACTION.md`).

Rules:
- Each assistant edits only its own section, and rewrites it when things change. Keep it current, not historical.
- Say what you did, what you want from the other side, and what you are about to do.
- One line per finished action also goes into `ACTION.md`.
- No secrets, tokens or personal data. Changes reach `main` by PR like any other border file.

### Fasih's assistant (skills side)

**Last updated:** 2026-11-15

**What I did**
- Reviewed the whole project at `9db7095` and the `t16-alerts-http-dashboard` branch at `e304196`. Every finding was reproduced before it was written down. Result: `docs/HAMZA_REVIEW.md` (sections 1 to 5).
- Fixed ten faults in the skill runner and built the rest of the Phase 1 skills side: seed corpus with a checksum manifest, T-08 inventory and sweep, T-10 watcher, T-11 collector, T-15 profile. All merged (PRs #2, #4 to #8). Commands live under `python -m cim.skills`.
- Drafted the threat model (`t03-threat-model`, not merged) and the dashboard research notes asked for in `docs/FASIH_DASHBOARD_RESEARCH.md` (merged, `docs/DASHBOARD_RESEARCH_NOTES.md`).
- Wrote three contract fixes (canonical JSON rejects unhashable strings, stray artefact ids, real timestamps) and draft answers to the four v1.1 rows. They are on Fasih's machine only, waiting for agreement.
- Did not edit anything under `src/cim/mcp/`, `src/cim/dashboard/` or `src/cim/common/store/`.

**What I want from Hamza's assistant**, most urgent first
1. **Store, two writers (S1).** The skills watcher and collector are merged and will write to the same store as the proxy. Today that breaks the chain without any attack.
2. **Store, what the hash covers (S2).** A decision is needed before either side keeps a store: it changes every stored hash.
3. **The demo alert (X2).** The dashboard's "change" button writes a fixed behaviour alert itself. Say whether that is meant to be shown at the December demo.
4. **The gateway (G1 to G3) and the dashboard write endpoints (X1)** before `t16-alerts-http-dashboard` merges.
5. **Proxy fail-open (P1) and drift bypasses (D1 to D3).**
6. **Contract v1.1:** react to the draft answers once Fasih shares them, so one revision covers both sides.
7. **Dashboard:** skill records are shown as MCP records (U1). Tell me which shape the board wants and I will provide the skills read model.

**What I am about to do**
- Fasih has asked me to take on the pending items from the review while Hamza is busy. Agreed rules: one stage at a time, Fasih approves each stage before it starts, one branch and one PR per stage, and **Hamza merges**. Nothing in Hamza's code reaches `main` without him.
- **Stage 1, in progress (2026-11-15): baseline store.** Branch `t06-store-fixes`. Two writers (S1), artefact lookup (S5), tip hash and count in `verify-chain` (S3), real timestamps (S4). S2 (what the hash covers) is **not** changed: it alters the formula in the plan and needs both of us.
- Planned next, not started: 2. proxy (P1, P2, P3, D1); 3. drift and inventory (D2 to D5, C1); 4. dashboard and envelope on `main` (U1, U2, E1); 5. the unmerged T-16 branch (G1 to G5, X1, X2).

### Hamza's assistant (MCP side)

**Last updated:** —

**What I did**
- _(to be written by Hamza's assistant)_

**What I want from Fasih's assistant**
- _(to be written by Hamza's assistant)_

**What I am about to do**
- _(to be written by Hamza's assistant)_
