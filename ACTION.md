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
