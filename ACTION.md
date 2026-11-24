# ACTION — what was done, by whom

One line per finished action, oldest first. Both assistants append here; nobody edits old lines. What each side wants from the other is in `CONTEXT.md`, not here.

- **Who:** `F-assistant` (Fasih's AI assistant), `H-assistant` (Hamza's AI assistant), `Fasih`, `Hamza`.
- **Where:** a PR, a branch or a file, so the action can be checked.
- No secrets or tokens.

| Date | Who | Action | Where |
|------|-----|--------|-------|
| 2026-11-15 | F-assistant | Reviewed the whole project at `9db7095`; reproduced and wrote up 23 findings on the store, proxy, drift, inventory, envelope, CLI and dashboard | `docs/HAMZA_REVIEW.md`, PR #3 |
| 2026-11-15 | F-assistant | Fixed ten faults in the skill runner (missed leaks, sub-cgroup hiding, crashes on non-UTF-8 output, relative paths, orphans on timeout) | PR #2 |
| 2026-11-15 | F-assistant | Posted the T-06 store review as a comment | PR #1 |
| 2026-11-15 | F-assistant | Added the seed corpus (11 benign, 3 inert suspicious skills) with a checksum manifest and verifier | PR #4 |
| 2026-11-15 | F-assistant | Built T-08: skill baselines and a sweep that records each changed file once | PR #5 |
| 2026-11-15 | F-assistant | Built T-10: integrity watcher (notifications plus periodic sweep) | PR #6 |
| 2026-11-15 | F-assistant | Built T-11: behaviour collector on a syscall trace; fixed two Ubuntu differences found by CI | PR #7 |
| 2026-11-15 | F-assistant | Built the T-15 per-skill profile (feature half) | PR #8 |
| 2026-11-15 | F-assistant | Reviewed `t16-alerts-http-dashboard` at `e304196`; added 11 findings on the gateway, dashboard and alert rule | `docs/HAMZA_REVIEW.md` section 5, PR #3 |
| 2026-11-15 | F-assistant | Drafted the threat model v0.9 | branch `t03-threat-model` (not merged) |
| 2026-11-15 | F-assistant | Wrote the dashboard research notes asked for in `docs/FASIH_DASHBOARD_RESEARCH.md` | `docs/DASHBOARD_RESEARCH_NOTES.md`, PR #9 |
| 2026-11-15 | F-assistant | Wrote three contract fixes and draft answers to the v1.1 rows | Fasih's machine only (branch `t02-contract-fixes`, not pushed) |
| 2026-11-15 | Hamza | Merged PRs #2 to #9 into `main` (seen in the repo, not written by Hamza) | org `main` at `7b9f3c5` |
| 2026-11-15 | F-assistant | Added the assistant exchange to `CONTEXT.md` and created this file | branch `t01-assistant-exchange` |
| 2026-11-15 | Fasih | Asked F-assistant to fix the open review findings in stages, one PR per stage, for Hamza to merge | `CONTEXT.md` |
| 2026-11-15 | F-assistant | Started Stage 1: baseline store fixes S1, S3, S4, S5 (S2 left for a joint decision) | branch `t06-store-fixes` |
| 2026-11-15 | F-assistant | Finished Stage 1: store fixes S1, S3, S4, S5 with 10 new tests; S2 left open | PR #11 (for Hamza to merge) |
| 2026-11-15 | F-assistant | Started Stage 2: stdio proxy fixes P1, P2, P3 and the proxy half of D1 | branch `t09-proxy-fixes` |
| 2026-11-15 | F-assistant | Finished Stage 2: proxy fixes P1, P2, P3 and the proxy half of D1, with 7 new tests | PR #12 (for Hamza to merge, after #11) |
| 2026-11-15 | F-assistant | Started Stage 3: drift and inventory fixes D1 (drift half), D2 to D5, C1 | branch `t12-drift-fixes` |
| 2026-11-15 | F-assistant | Finished Stage 3: drift and inventory fixes D1 to D5 and C1, with 14 new tests | PR #13 (for Hamza to merge, after #11 and #12) |
| 2026-11-18 | Hamza | Merged PRs #10–#13 into org `main` (maintainer merge only; commits authored by fasih-moin; no AI/Cursor co-author) | org `main` at `1b71563` |
| 2026-11-18 | H-assistant | Filled Hamza’s assistant section in `CONTEXT.md`; recorded merges in this file | `CONTEXT.md`, `ACTION.md` |
| 2026-11-19 | H-assistant | Rebased T-16/T-16b onto org `main`; fixed Fasih High G1–G3 and X1–X2; live T-16 and T-16b alerts OK | branch `t16-alerts-on-main` |
| 2026-11-19 | H-assistant | Shipped T-16/T-16b; opened PR; `ci-push` + `merge-gate` green | [PR #16](https://github.com/ContinuousIntegrityMonitor/Final_Year_Project/pull/16) (`db548aa`…`e974f67`) |
| 2026-11-19 | H-assistant | Rewrote `CONTEXT.md` Active-now + Hamza exchange; refreshed `PROJECT_STATUS.md` and T-16b progress task | `CONTEXT.md`, `PROJECT_STATUS.md`, `progress/tasks/T-16b-http-mcp-gateway.md` |
| 2026-11-19 | Hamza | Merged PR #16 (T-16/T-16b + G1–G3/X1–X2) into org `main`; no AI co-author | org `main` at `e27f6dd` |
| 2026-11-19 | H-assistant | Synced local `main` and `fresh/main` to `org/main` (`e27f6dd`) | local `main`, `fresh/main` |
| 2026-11-19 | H-assistant | Merged status docs after #16 | PR #17 → `main` |
| 2026-11-19 | H-assistant | Asked Fasih only: implement U1/A2/S2/contract; pull `main`; run MCP unit + live tests; file `docs/FASIH_MCP_TEST_REPORT.md` with improvements | `docs/FASIH_ASK_2026-11-19.md`, `CONTEXT.md` |
| 2026-11-23 | F-assistant | Tested org `main` @ `a816817` (suites, live T-16/T-16b stand-ins, verify-chain, dashboard, gateway refusals); wrote report with 2 High / 5 Medium / 7 Low suggestions | `docs/FASIH_MCP_TEST_REPORT.md`, `scripts/live_t16_stdio.py`, `scripts/live_t16b_http.py` |
| 2026-11-24 | F-assistant | Stage U1: skills read model for the status board (`cim.skills.board`, `python -m cim.skills board`), shape doc with a tested `load_board` wiring diff, 14 tests | branch `t15-skills-board`, `docs/U1_SKILLS_BOARD_SHAPE.md` |
| 2026-11-24 | F-assistant | Shared scorer design note with a prototype threshold sweep on real stores (560 traced skill runs, 300-call MCP replay) | branch `t16-scorer-design`, `docs/T16_SHARED_SCORER_DESIGN.md` |
| 2026-11-24 | F-assistant | T-17 skills attacks: inert trigger skill `meeting-brief` (A3), `word-count` legitimate update (A4), `python -m cim.skills attack`; 8 tests; 10/10 reliable each | branch `t17-skills-attacks`, `progress/tasks/T-17.md` |
| 2026-11-24 | F-assistant | Docs stage: ADR-006 S2 proposal (re-reproduced), threat model v0.10 (status per gap), T-05/08/10/11/15 marked Done | branch `t03-s2-threat-cleanup`, `docs/decisions/ADR-006-record-hash-coverage.md`, `docs/THREAT_MODEL.md` |
| 2026-11-24 | F-assistant | T-13 pipeline and CLI design note (config, command map, watchdog, status, acceptance test); T-13 progress file | branch `t13-pipeline-design`, `docs/T13_PIPELINE_DESIGN.md`, `progress/tasks/T-13.md` |
| 2026-11-24 | Fasih | Posted the PR summary and merge order for Hamza on issue #19 | issue #19 comment |
| 2026-11-24 | Fasih | Agreed all four drafted answers to Hamza's v1.1 contract request | `docs/FASIH_REVIEW.md` |
| 2026-11-24 | F-assistant | Contract 1.0.1 (B1 to B3) and 1.1.0 (four rows + scorer, watchdog, P4, D3 fields), additions only; 29 tests | branch `t02-contract-v1-1`, `docs/CONTRACT_V1_1.md` |
| 2026-11-24 | Hamza | Reviewed and merged Fasih PRs #20–#26 (merge commits; author HamzaFarooq3333; no AI/Cursor co-author) | org `main` @ `fa869ce` |
| 2026-11-24 | H-assistant | Synced local `main` to `org/main`; refreshed status after #20–#26 | `CONTEXT.md`, `ACTION.md`, `PROJECT_STATUS.md` |
| 2026-11-24 | H-assistant | H1: gateway requires token before Bearer; refuse Origin null / non-JSON POST; U1 wired into dashboard MCP+Skills panels; ADR-006 accepted (code later) | `http_gateway.py`, `board.py`, `page.py`, `docs/setup/cursor-http-mcp-gateway.md` |
| 2026-11-24 | F-assistant | Checked org `main` @ `d25ef41` after #27/#28: 355 tests, both live scripts PASS, H1 closed (gateway exits 2 without token), U1 wired; M2, M3, M5, L1 re-tested open. Refreshed CONTEXT, threat model v0.11, test report follow-up, progress T-02/03/13/15/17 | branch `t01-status-after-28` |
