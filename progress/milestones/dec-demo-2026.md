# December 2026 demo — C1–C6

- **Status:** not achieved yet. None of C1–C6 has been shown live on VM-MON. C1 and C3 pass with recorded or stand-in input; C2 and C4 pass on stand-in servers only; C5 is partial; C6 is not started.
- **Checked:** 2026-11-24, on org `main` @ `d25ef41` (after PR #28), Fedora 44. Drafted by F-assistant for both to verify (joint file).
- **Suite:** `uv run pytest -m "not lab"` → 355 passed, 0 skipped. No test carries the `lab` marker yet, so nothing in CI touches HexStrike or a VM.
- **Target date:** the week of 14 December 2026, with a dry run the week before (plan section 2.1; Hamza confirmed it on 2026-11-25).
- **Scope:** ADR-003. Criteria wording below is from the plan, section 2.1.

## Criteria

**C1 — `cim inventory` shows every bound MCP tool (with schema digests) and every installed skill (with content hashes), all in the append-only store.** Partly achieved.
- Done: `uv run cim inventory --db S --tools-json corpora/mcp/tools_list.json` → `tools=150 … chain=ok pin=written`. The list is the pinned HexStrike `tools/list` (commit `d689933`), recorded on the dev PC, not on VM-MON.
- Done: `uv run python -m cim.skills inventory --db S --root corpora/skills` → `skills=15 new_baselines=15 chain=ok` into the same store; `cim verify-chain --db S` → `ok (167 records)`. Corpus manifest: `python -m cim.skills corpus verify` → `manifest verifies` (11 benign, 4 suspicious; T-05 PRs #2, #4, T-17 PR #23).
- Open: it is two commands, not one `cim inventory`. Making `inventory` cover both sides is in the T-13 design (`docs/T13_PIPELINE_DESIGN.md`, PR #25), not coded.
- Open: no inventory has been taken on VM-MON.

**C2 — Live benign session against HexStrike through the proxy; every tool call captured and visible.** Not achieved live.
- Done (stand-ins): `tests/mcp/test_proxy.py::test_scripted_replay_logs_100_calls_in_order` and `::test_real_mcp_client_session_through_proxy`. `scripts/live_t16_stdio.py` (real MCP SDK client → `cim proxy` → SDK server) → 37 behaviour records, `RESULT: PASS`. `scripts/live_t16b_http.py` (HTTP gateway) → 36 behaviour records, `RESULT: PASS`.
- Visible: `cim dashboard --db S` shows calls, tools and changes, with separate MCP and Skills panels since PR #28.
- Open: no session against HexStrike. VM-MON is not built.
- Open, HTTP path only (re-tested with `live_t16b_http.py` probes c and d on `d25ef41`): an SSE stream's first event reaches the client only when the stream ends (M2); two clients reusing request id 7 give 2 calls but 1 record (M3). Details: `docs/FASIH_MCP_TEST_REPORT.md` section 5.

**C3 — Rug-pull live: swapping to a backdoored server version fires a schema-drift alert with a human-readable diff.** Achieved on recorded input; not live.
- Done: `uv run cim sweep --db S --tools-json <HexStrike list with nmap_scan's description changed and a bcc parameter added>` → `nmap_scan: description changed`, `nmap_scan: added parameter bcc (string)`; a second sweep → `still differs from the pin (2 differences, already recorded)`; chain ok.
- Tests: `tests/mcp/test_drift.py` (`test_backdoor_names_tool_and_parameter`, `test_proxy_pins_first_list_and_records_later_drift`, and the D1–D5 cases from PR #13); `tests/mcp/test_dashboard.py::test_board_shows_pin_call_and_rug_pull` (the dashboard's `send_email` demo server with a hidden `bcc`).
- Note: the alert names the tool and what changed (field, parameter and type). It does not print the old and new description text.
- Open: no backdoored HexStrike version swapped in on VM-MON. The MCP half of the attack pack (A1, A2) is Hamza's part of T-17 and is not in the repo yet.

**C4 — Trigger-payload live: a trigger tool fires a behavioural alert naming the drifted feature, while the artefact hash is shown unchanged.** Not achieved live.
- Done (MCP, stand-ins): the rule-based MCP alert `cim/mcp/alert.py` `score_latest` (PR #16). Both live scripts give one `mcp_behaviour_drift` alert naming `value class private_ip` after 30 warm-up calls (output above).
- Open: the shared scorer (T-16, `src/cim/common/scorer.py`) is not coded. Its design (`docs/T16_SHARED_SCORER_DESIGN.md`, PR #22) waits on the six decisions in its section 11. The MCP rule above is not the scorer: it has no threshold, and an unusual call joins the baseline, so a repeated attack alerts once (review A1).
- Skills side (a stretch goal in the plan): `uv run python -m cim.skills attack A3 --work <empty dir>` → tree digest unchanged, sweep records no file change, the run after the trigger has a never-seen destination, `PASS`. But no alert record is written: the store holds 15 artefact and 31 behaviour records, and `python -m cim.skills board --json` shows `alerts: 0`. The alert waits on the scorer.
- Open: no trigger tool against HexStrike; nothing run on VM-MON.

**C5 — `cim status` shows inventory, events, alerts; chain verification passes.** Partly achieved.
- Done: `uv run cim verify-chain --db S` → `ok (N records) tip=…`; `--expect-tip` and `--min-count` catch a chain cut short (PR #11, `tests/common/test_store.py::test_cli_catches_a_chain_that_was_cut_short`).
- Done: `cim dashboard --db S` shows tools, calls, changes and alerts, with MCP and Skills panels (PR #21 read model, wired in PR #28).
- In review (PR `T-13: cim status and cim events`): `cim status` shows store and chain, inventory (both sides), findings as changed artefacts, behaviour alerts, monitor events, capture faults and learning state; `--json`; exit 0 clean / 1 otherwise. `cim events` lists every record by side. Checked on a live `cim proxy` store (1 MCP behaviour alert) and an A3 store (1 skill alert), both exit 1.
- Open: the `collectors` line, and exit 2 for a monitor that is not running, come with `cim watch` (T-13 stage 4). Not run on VM-MON.

**C6 — Backup video recorded; demo script committed to the repo.** Not achieved.
- No demo script is in the repo (searched `docs/` and the root). No video recorded. Both belong to T-18 (rehearsals), which has no progress file yet.

## Building blocks

State on org `main` @ `d25ef41`. "Task file" is what `progress/tasks/T-XX.md` says, where it differs.

| Task | State | Evidence |
|---|---|---|
| T-01 infra / CI | Done | `ci-push` and `merge-gate` workflows; assistant exchange PR #10 |
| T-02 contract | 1.0, then 1.0.1 and 1.1.0 merged (additions only) | `637b043`; PR #26, `tests/common/test_schema_v11.py`. MCP writers have not adopted the 1.1 fields yet (`docs/CONTRACT_V1_1.md` section 3) |
| T-03 threat model | Draft v0.10 on `main` | PR #24. v0.11 and v0.12 are in open PRs #29 and #30. Waits on Hamza's review of the MCP rows, then the adviser |
| T-04 MCP lab | Done (pin, topology, harness) | `0d87cf9`; pin `corpora/mcp/hexstrike.pin`; 150-tool list `corpora/mcp/tools_list.json`. VM-MON itself is not built |
| T-05 skills runner + corpus | Done | PRs #2, #4; `corpus verify` |
| T-06 baseline store | Merged; fixes S1, S3–S5 merged | PRs #1, #11. ADR-006 (S2) accepted in PR #28; its hash-formula code is not written. Task file: IP |
| T-07 MCP inventory | On `main` since 2026-11-09 | merge `d1af665` (no PR); `cim inventory` above. Task file: IP |
| T-08 skills inventory | Done | PR #5 |
| T-09 MCP proxy | On `main` since 2026-11-09; fixes P1–P3 merged | `d1af665`; PR #12. Task file: IP |
| T-10 skills watcher | Done | PR #6 |
| T-11 behaviour collector | Done | PR #7. Helper / monitor boundary: ADR-007 in open PR #30 |
| T-12 rug-pull detector | On `main` since 2026-11-09; fixes D1–D5, C1 merged | `d1af665`; PR #13. Task file: IP |
| T-13 pipeline / `cim` CLI | In progress: config loader and CLI restructure in review | PR #25 (design), #34 (agreed), #51 (config loader), PR `T-13: cli.py restructure`; `cim status` is still a stub |
| T-14 MCP envelope | On `main` since 2026-11-09 | `d1af665`; `cim envelope`. Task file: IP |
| T-15 skills profile | Done (feature half); read model wired into the dashboard | PRs #8, #21, #28 |
| T-16 scorer | Shared scorer on `main`, both sides alert; threshold sweep recorded | PRs #42, #43, #46, #47, #49; `docs/results/T16_threshold_sweep.md`. No `progress/tasks/T-16.md` |
| T-16b HTTP gateway | Merged; H1 fixed | PRs #16, #28. M2, M3, M5, L1 still reproduce. Task file still says "PR open" |
| T-17 attack pack | Skills half (A3, A4) built; MCP half (A1, A2) not in the repo | PR #23; `python -m cim.skills attack A3\|A4` |
| T-18 rehearsals + video | Not started | no task file, no demo script |

## Still open for December

- VM-MON is not built anywhere yet, so nothing has run on it: no HexStrike session (C2), no rug-pull swap (C3), no trigger (C4). It will be built on Fasih's machine, and the demo runs there (Fasih, 2026-11-25).
- T-13 is in progress: a single two-sided `cim inventory` (C1) comes with the CLI restructure PR, `cim status` (C5) with the status PR; `cim watch` is next.
- No live HexStrike call has been made through the proxy or gateway.
- No backup video and no demo script (C6, T-18).

## Remotes

Push accepted phases to both `origin` and `org` (ADR-002). Do not push the pre-rebuild history.
