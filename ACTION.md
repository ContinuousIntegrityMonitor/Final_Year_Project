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
| 2026-11-24 | Fasih | Decided the T-11 helper / monitor boundary: one user and a precise claim for FYP I; monitor and store as their own user for FYP II | `docs/decisions/ADR-007-skills-monitor-boundary.md` |
| 2026-11-24 | F-assistant | Wrote ADR-007; threat model v0.12 (6.2 wording); T-13 note decision 8 (one store writer); T-11 progress and module docstrings | branch `t11-boundary-adr` |
| 2026-11-24 | F-assistant | Rewrote the December milestone (C1 to C6, building blocks) against org `main` @ `d25ef41` with evidence per claim; drafted history entries for Fasih PRs #11–#13 and #20–#26 (author verifies) | branch `t01-milestone-history-refresh`, `progress/milestones/dec-demo-2026.md`, `history/entries/PR-0011_T-06.md` … `PR-0026_T-02.md` |
| 2026-11-24 | F-assistant | Added the history entry for PR #10; re-checked all 11 entries against merge diffs and `main`; fixed the scorer sweep count (680, not 690); found that contract 1.1 (#26) changed every MCP tool and manifest digest (the `tool_digest: null` key), reported, not fixed | branch `t01-milestone-history-refresh`, `history/entries/PR-0010_T-01.md`, `PR-0026_T-02.md` |
| 2026-11-24 | F-assistant | Fixed the MCP digest shift from contract 1.1: per-tool and manifest digests cover the three 1.0 descriptor fields only, pre-1.1 values restored (HexStrike manifest `f937f478…`); 2 pinning tests; contract note corrected | branch `t07-digest-stability`, `src/cim/mcp/inventory.py`, `tests/mcp/test_inventory.py` |
| 2026-11-24 | F-assistant | Added `python -m cim.skills exec`: one helper run in its scope under the collector for an agent harness, recorded through one store function, stdout/stderr/exit code passed back; refuses scripts outside the skill (126), unknown skills (127), runs without a tracer (125); 19 tests, 376 passed; checked by hand on 5 corpus skills incl. `meeting-brief` A3 trigger | branch `t11-skills-exec`, `src/cim/skills/execute.py`, `tests/skills/test_skills_exec.py` |
| 2026-11-24 | Hamza | Reviewed and merged Fasih PRs #29–#33 (merge commits; author HamzaFarooq3333; no AI/Cursor co-author) | org `main` after #33 |
| 2026-11-24 | H-assistant | Green light: scorer §11 (1–5 agree; Hamza owns MCP switch) and T-13 §10 (1–6+8 agree; Hamza takes MCP pieces in 7); H2 keep stand-ins; next = contract 1.1 writers (M1) | `CONTEXT.md` |
| 2026-11-24 | H-assistant | Contract 1.1 MCP writers: chained behaviour + session + pin under mcp_server + integrity detail + tool_digest + Event validation | `src/cim/mcp/proxy.py`, `events.py`, `drift.py`, `inventory.py` |
| 2026-11-24 | Hamza | Merged PR #35 (contract 1.1 MCP writers) to org `main` | PR #35 → `main` @ `4d0c8ac` |
| 2026-11-24 | H-assistant | Status refresh: CONTEXT / PROJECT_STATUS / Hamza task files T-07/09/12/14/16b Done | `CONTEXT.md`, `PROJECT_STATUS.md`, `progress/tasks/` |
| 2026-11-24 | H-assistant | Windows ship gates: posix skill paths in `digest.record_path`; `_prepush_ci.sh` runs common+MCP only on Windows (full suite stays on Ubuntu CI) | `src/cim/skills/digest.py`, `scripts/_prepush_ci.sh`, `scripts/_ship.sh` |
| 2026-11-24 | H-assistant | Fixed ship hang: `prepush_local.sh` had no `--help`, so the scripts-help loop re-entered the full gates; add `--help`, skip self, skip check-env on Windows; refresh status MDs | `scripts/prepush_local.sh`, `CONTEXT.md`, `PROJECT_STATUS.md`, `progress/tasks/` |
| 2026-11-24 | H-assistant | Status refresh after #35: CONTEXT Active-now + Hamza exchange; PROJECT_STATUS; T-07/09/12/14/16b → Done | `CONTEXT.md`, `PROJECT_STATUS.md`, `progress/tasks/` |
| 2026-11-24 | Hamza | Merged PR #36 (Windows ship gates / prepush_local --help recursion) to org `main` | PR #36 → `main` @ `384882f` |
| 2026-11-24 | H-assistant | MCP `score_latest` reads chained behaviour (1.1 fields); no longer scores from `envelope_obs` (M1) | `src/cim/mcp/alert.py`, `tests/mcp/test_behaviour_alert.py` |
| 2026-11-24 | Hamza | Merged PR #37 (MCP score_latest chain switch / M1) to org `main` | PR #37 → `main` @ `0ab17e6` |
| 2026-11-24 | H-assistant | M2 SSE stream, M3 session-keyed Capture, M5 Host on GET, L1 encoded path escape | `src/cim/mcp/http_gateway.py`, `proxy.py`, `dashboard/serve.py` |
| 2026-11-24 | Hamza | Merged PR #39 (M2/M3/M5/L1) to org `main` | PR #39 → `main` @ `c5f1ac3` |
| 2026-11-24 | H-assistant | ADR-006 hash v2: chain covers ts, artefact_id, artefact row; v1 stores verify-only | `src/cim/common/chain.py`, `store/baseline.py`, tests |
| 2026-11-24 | Hamza | Merged PR #40 (ADR-006 hash v2 + SSE capture-on-disconnect) to org `main` | PR #40 → `main` @ `4cdb861` |
| 2026-11-24 | H-assistant | Status refresh after #40 | `CONTEXT.md`, `PROJECT_STATUS.md`, `progress/tasks/T-06.md` |
| 2026-11-25 | H-assistant | Shared scorer library (integer milli-z, A1 baseline) | PR #42 → `main` |
| 2026-11-25 | Hamza | Merged PR #42 (shared scorer) to org `main` | PR #42 |
| 2026-11-25 | H-assistant | MCP `score_latest` wired to shared scorer (A1 + BehaviourAlertPayload) | PR #43 → `main` |
| 2026-11-25 | Hamza | Merged PR #43 (MCP scorer wire) to org `main` | PR #43 |
| 2026-11-25 | H-assistant | Ask Fasih: review #42/#43; skills alerts; T-13 shared; live demo prep | `docs/FASIH_ASK_2026-11-25.md`, `CONTEXT.md` |
| 2026-11-25 | F-assistant | Reviewed #42 (shared scorer) and #43 (MCP wire) against the scorer design: parity OK; 1 bug (wrong record scored with two writers), 1 design question (every error alerts), test gaps, clean-up, cost | `CONTEXT.md` |
| 2026-11-25 | F-assistant | Skills behaviour alerts: record_behaviour scores each run with the shared scorer and writes skill_behaviour_drift (A3 10/10 alerts, A4 0/10) | `src/cim/skills/alert.py`, `collector.py`, `attacks.py`, `execute.py`, tests, T-15/T-17, U1 doc |
