# HANDOFF — CIM, skills side

- **Written:** 2026-11-15, by Fasih's AI assistant, for Fasih (and for whichever assistant session picks this up next). **Sections 1, 4, 5 and 7 rewritten 2026-11-24** after Hamza merged #20 to #28, and brought up to date again after PRs #29 to #32 were opened; sections 2, 3 and 6 are the record of how the early work was done; 8 onward is the log per stage.
- **Tracked in the repo since 2026-11-25** (Fasih asked for it to be pushed). It is Fasih's side's working log: what was done, how, and what remains. The files both sides write to are `CONTEXT.md` (what each assistant did and wants) and `ACTION.md` (the log).

## 1. Where things stand (2026-11-24)

Org `main` @ `d25ef41` holds everything. Hamza merged all my PRs (#2 to #26) and shipped #27 (status) and #28 (H1 gateway fix + U1 dashboard panels). Checked after #28: 355 tests pass, ruff and mypy clean, both live scripts PASS. CI green.

| Piece | PR | State |
|---|---|---|
| Skills side T-05, T-08, T-10, T-11, T-15 (feature half) | #2, #4 to #8 | Done |
| Store / proxy / drift fixes (Stages 1 to 3) | #11 to #13 | Merged |
| MCP test report + live stand-in scripts | #20 | Merged; follow-up in its section 5 |
| U1 skills read model | #21 | Merged; **wired into the dashboard by Hamza in #28** |
| Scorer design note (T-16) | #22 | Merged; **waiting on Hamza's 6 decisions (section 11)** |
| T-17 skills attacks A3 / A4 | #23 | Merged; detection waits on the scorer |
| Threat model v0.10, ADR-006, progress cleanup | #24 | Merged; ADR-006 **accepted** by Hamza (#28); threat model v0.11 in #29, v0.12 in #30 |
| T-13 pipeline / CLI design note | #25 | Merged; **waiting on Hamza's 8 decisions (section 10; decision 8 comes with #30)** |
| Contract 1.0.1 + 1.1.0 | #26 | Merged; MCP writers adopt in Hamza's next proxy PR. It shifted the MCP digests; fixed in #32 |
| Status refresh after #28, threat model v0.11 | #29 | Open, CI green (section 15) |
| T-11 boundary: ADR-007, threat model v0.12 | #30, stacked on #29 | Open, CI green (section 16) |
| December milestone + 11 history drafts | #31, stacked on #30 | Open, CI green (section 17) |
| MCP digest stability fix (Hamza's `inventory.py`) | #32, stacked on #31 | Open, CI green (section 18) |
| `python -m cim.skills exec` (T-11) | #33, stacked on #32 | Open (section 19) |

Merge order for Hamza: #29 → #30 → #31 → #32 → #33. Local branch: `t11-skills-exec`.

Hamza asked (CONTEXT, his section): hold `common/scorer.py` and the T-13 CLI work until he answers. Nothing has been pushed to `origin` (Hamza's personal repo; ADR-002). Nothing has run on VM-MON: it does not exist yet.

## 2. What I did, in order

1. **Reviewed the whole project** and reproduced every suspected flaw before writing it down. Fixed the ones in `src/cim/skills/`; wrote the rest into `docs/HAMZA_REVIEW.md` (23 findings on the store, proxy, drift, inventory, envelope, CLI and dashboard).
2. **Fixed ten runner faults.** The serious ones: a helper that exited in milliseconds could leave a daemon behind unseen (missed 10 of 10 runs); a process could hide in a sub-cgroup; non-UTF-8 output crashed the run; a timeout left children running.
3. **Finished T-05:** 14 corpus skills (11 benign, 3 inert suspicious stand-ins) with `MANIFEST.json`, a verifier, and a run of every corpus skill.
4. **Built T-08, T-10, T-11 and the T-15 profile.**
5. **Reviewed Hamza's `t16-alerts-http-dashboard` branch** and added 11 findings (section 5 of the review notes).
6. **Drafted** the threat model (T-03), the dashboard research notes Hamza's brief asked for, three contract fixes, and answers to Hamza's four v1.1 contract rows.

## 3. How I did it

**Method**
- **Reproduce first.** Each suspected bug got a small script that showed it failing before any fix or write-up. Nothing in the review notes is from reading alone unless it says so.
- **One regression test per fix**, then the full gates: `ruff format --check`, `ruff check`, `mypy src/cim`, `pytest -m "not lab"`.
- **Repeat timing-sensitive tests** three to seven times before trusting them.
- **One branch per task**, stacked in task order, each pushed so CI ran on Ubuntu.
- **Stayed out of Hamza's territory.** No edits under `src/cim/mcp/`, `src/cim/dashboard/` or `src/cim/common/store/`. Schema fixes stayed on a local branch because the plan requires both reviewers and a version bump.
- **No AI attribution** in any commit, PR or comment.

**Design choices worth knowing**
- **Start gate (scoped runner).** The helper waits behind `sh -c 'read && exec'` until its cgroup is known. That turned the leak check from a race into a certainty.
- **Membership is read recursively**, so a sub-cgroup inside the scope hides nothing.
- **Plain runner uses a process group**, killed on timeout and after exit.
- **Store view of a skill = baseline + later integrity events.** A change is reported once, and the first baseline is never rewritten.
- **Watcher: notifications only trigger a sweep.** Every event comes from comparing hashes, so the notification path and the periodic path cannot disagree.
- **Collector uses `strace -f`, not `/proc` polling** (a deviation from the plan, recorded in `progress/tasks/T-11.md`). Polling saw 1 process where the trace sees 5 on `dep-installer`, and cannot see a refused connection.
- **Trace parser lifts every quoted string and `<...>` path out of a line first**, so a file name cannot forge a call, a result or an exit line.
- **Profiles are derived on demand** from the hash-chained records; nothing is stored beside the chain.

**Things that bit me** (they will bite again)
- `pkill -f "sleep 47"` also matches the shell running the command. Anchor it: `'^sleep 47$'`.
- The GitHub runner's coreutils is one multi-call binary: copying `sleep` under another name does not run.
- On Ubuntu every program tries the name-service socket at start-up and gets `ENOENT`. A failed unix connect is therefore not recorded as egress.
- Python writes `.pyc` on first import on a fresh machine. Helpers run with `PYTHONDONTWRITEBYTECODE=1`.
- `ruff format .` also reformats Python code blocks inside Markdown files.
- The pre-commit ruff hook is pinned to v0.9.10 but CI uses the ruff from `uv.lock` (0.16). They disagree on import order in `tests/mcp/test_proxy.py`. If the hook rewrites that file, restore it and commit with `SKIP=ruff git commit ...` after running `uv run ruff check .` yourself.
- A rejected commit does not stop later lines of the same shell command. PR #12 was briefly opened pointing at the store commit only, because the hook rejected the commit and the push ran anyway. Check `git log` before pushing.
- The session scratchpad under `/tmp` was cleared at some point; the early repro scripts are gone. The tests in the repo now cover the same cases.
- Corpus files are excluded from ruff and from git line-ending conversion (`corpora/skills/ruff.toml`, `.gitattributes`), because their checksums are over exact bytes.

## 4. How to run things

```bash
uv run pytest -m "not lab"                       # full suite (355 on d25ef41, 357 with #32, 376 with exec)
uv run python -m cim.skills corpus verify        # manifest check (15 skills: 11 benign, 4 suspicious)
uv run python -m cim.skills corpus run           # run every corpus helper
uv run python -m cim.skills inventory --db S --root corpora/skills
uv run python -m cim.skills sweep     --db S --root corpora/skills
uv run python -m cim.skills watch     --db S --root corpora/skills
uv run python -m cim.skills observe   --db S [--skill notes-sync]
uv run python -m cim.skills exec      --db S [--root R] <skill> -- <script> [args]  # agent harness; -v says what was recorded
uv run python -m cim.skills envelope  --db S
uv run python -m cim.skills board     --db S [--json]      # U1 skills section
uv run python -m cim.skills attack A3|A4 --work <empty dir>  # T-17
uv run cim dashboard --db S                      # MCP + Skills panels since #28
uv run python scripts/live_t16_stdio.py . <new db>          # T-16 live stand-in
uv run python scripts/live_t16b_http.py . <empty dir>       # T-16b live stand-in + probes
```

The scoped runner needs a systemd user session; the collector also needs `strace`. Tests skip without them. Both are present here and on the GitHub runner.

## 5. What is remaining (2026-11-24)

**Waiting on Hamza (blocks my next code)**
- Scorer design decisions (section 11 of `docs/T16_SHARED_SCORER_DESIGN.md`) → then `common/scorer.py`, the skills call site, the sweep script.
- T-13 decisions (section 10 of `docs/T13_PIPELINE_DESIGN.md`) → then config loader, CLI restructure, `cim status` / `events`, `cim watch`, acceptance test. Window ends Dec W1.
- Adopting contract 1.1 MCP fields in the proxy (needed for M1).
- Threat model MCP rows review (T-03 to v1.0, then the adviser).

**Open on Hamza's side, re-tested 2026-11-24:** M2 (SSE held), M3 (same request id, lost call), M4 (faults not recorded; from reading), M5 (dashboard GETs skip Host), L1 (`%2e%2e`). ADR-006 store code (T-06).

**Waiting on Hamza (review only)**
- Merge or decline #29 → #30 → #31 → #32, in that order.
- CONTEXT items 6 to 8: the milestone's target date (plan: week of 14 Dec; `PROJECT_STATUS.md`: ~1 Dec) and VM-MON; his stale task files (T-07/09/12/14 say IP, T-16b says "PR open", no T-16 file); the #32 digest fix.

**Only you can do**
- Verify the 11 history drafts (`history/entries/PR-0010_T-01.md` … `PR-0026_T-02.md`) and delete each one's "Draft … Fasih to verify" line.
- ~~Decide the T-11 boundary~~: decided 2026-11-24, ADR-007 (see section 16).
- VM-MON: build it, or find out from Hamza whether it exists.
- T-18: rehearsals and the backup video, once the scorer and T-13 land.
- Adviser sign-off on the threat model after Hamza's review.

**Known limits I documented but did not fix**
- A helper running as the same user can move a process out of its cgroup, can tell it is traced, and can tamper with its own trace file. ADR-007 accepts these for December (claim worded in threat model 6.2) and closes them in FYP II (monitor and store as their own `cim` user).

## 6. The current request (2026-11-15)

You asked for: this file; `CONTEXT.md` and `ACTION.md` shared between the two assistants; Hamza's pending work from the review done as well, in stages, asking you before each stage; the GitHub repo kept up to date.

- **Stage 0 (done):** this file, the `CONTEXT.md` update, `ACTION.md`.
- **Your answers (2026-11-15):** fix Hamza's flaws; one PR per stage for Hamza to merge; start with the store.
- **Stage 1 (done): store, PR #11.** Every append now runs in a `BEGIN IMMEDIATE` transaction and reads the chain tip inside it, so several processes can write to one store. Added `find_artefact()` / `get_or_create_artefact()`, the tip hash in `verify-chain` with `--expect-tip` / `--min-count`, and real timestamp checking. 10 new tests; suite at 256. Speed on disk unchanged. S2 (what the hash covers) deliberately not touched.
- **Stage 2 (done): stdio proxy, PR #12**, stacked on #11. Capture is called through one guard, so no frame can stop forwarding; a frame capture could not handle, or an event the store could not take, leaves a `proxy_capture_failed` alert; `cim proxy` returns 127/126 instead of hanging when the server cannot start; later sessions reuse artefact rows. 7 new tests; suite at 263. The `invocation_id` format was left alone (it is part of the contract discussion).
- **Stage 3 (done): drift and inventory, PR #13**, stacked on #12. The diff can no longer be stopped by a nameless or odd entry; repeated names are reported and every copy compared; the whole tool object is compared (`title`, `annotations`, `outputSchema`, anything new); a list state is recorded once, using list digests stored in `old_sha256` / `new_sha256`; paginated lists are joined; `cim inventory` writes the pin. 14 new tests; suite at 277. Stored per-tool digests were left alone (contract question).
- Stage updates to `CONTEXT.md` and `ACTION.md` go on branch `t01-assistant-exchange` (PR #10) until it merges; code goes on its own branch off `main`.
- **Stages for Hamza's pending items**, each on its own branch off `main`, with tests and a PR, logged in `ACTION.md`. Each needs your go-ahead.
  1. ~~Store~~ done, PR #11.
  2. ~~Proxy~~ done, PR #12.
  3. ~~Drift and inventory~~ done, PR #13.
  4. Dashboard and envelope on `main`: skill records mislabelled (U1), load (U2), read path that writes (E1).
  5. Hamza's unmerged T-16 branch: gateway G1 to G5, dashboard X1, X2. The most intrusive stage, since it is his work in progress.

**One thing to settle first:** the plan says Fasih does not push to `src/cim/mcp/` without Hamza's written agreement. PRs that Hamza merges himself respect that; merging them yourself would not.

## 7. Local-only things on this laptop

- `HANDOFF.md` (this file).
- Branch `t02-contract-fixes`: superseded (its two commits are in #26); safe to delete.
- `scratch/pr1-t06-review-comment.md`, `scratch/pr-review-notes-body.md`: texts already posted; safe to delete.
- Stale local branches whose work is merged: `t05-*`, `t08-skills-inventory`, `t10-skills-watcher`, `t11-host-collector`, `t15-skills-envelope`, `t15-skills-board`, `t16-scorer-design`, `t17-skills-attacks`, `t03-s2-threat-cleanup`, `t13-pipeline-design`, `t02-contract-v1-1`, `t01-fasih-mcp-test-report`, `t06-review-notes`, `t34-dashboard-research`. Org branch `t03-threat-model` is superseded too.
- Session scratchpad prototypes (scorer, supervisor, MCP replay) live under `/tmp` and will be lost on reboot; the numbers they produced are in the design notes.

## 8. Hamza's ask of 2026-11-19 (issue #19)

Hamza merged PRs #10 to #18 (our Stages 1 to 3, his T-16/T-16b with G1 to G3 and X1 to X2), then asked for two things in `docs/FASIH_ASK_2026-11-19.md`: A (implement U1, A2 shared scorer, S2 package, contract PR) and B/C (pull `main`, test the MCP side, write a report).

- **B/C done (2026-11-23):** branch `t01-fasih-mcp-test-report` off org `main` @ `a816817`, PR `T-01: Fasih MCP test report`. Report `docs/FASIH_MCP_TEST_REPORT.md`; new `scripts/live_t16_stdio.py` and `scripts/live_t16b_http.py`.
  - All green: 286 unit / 288 with sys / 66 MCP; ruff, mypy clean. Both live paths alert on `private_ip`; refusals all 401.
  - Hamza's `scripts/_live_t16*.py` are not in git (`.gitignore` has `scripts/_*`), hence the stand-ins. No Node on this laptop, so the stdio run uses `tests/mcp/sdk_server.py`, not Playwright.
  - Main findings: H1 gateway attaches the stored Bearer with no gateway token (the documented default) and accepts `Origin: null`; M1 scorer reads unchained `envelope_obs` (one UPDATE silences an alert); M2 SSE buffered; M3 same JSON-RPC id across sessions loses a call; M4 gateway/scorer faults not recorded; M5 dashboard GET has no Host check.
  - CI runs every `scripts/*` file with `--help`, and gitleaks scans the tree: new scripts need argparse and no key-looking strings.
- **A not started.** Order proposed: A1 U1 + Stage 4, A2 shared scorer, A3 S2 package, A4 contract PR (could carry M1 if Hamza picks that route). Each needs Fasih's go-ahead.

## 9. Stage U1 (2026-11-24)

- Branch `t15-skills-board`, stacked on `t01-fasih-mcp-test-report` (PR #20) so the `CONTEXT.md` edits do not conflict. Merge order: #20, then U1.
- New `src/cim/skills/board.py`: `is_skill_payload`, `skills_board(records)` (pure, over records the board already read), `as_dict` (shape version 1), `rail_label`, `render`. CLI `python -m cim.skills board --db S [--json]`; refuses a missing store instead of creating one.
- Small refactor: `inventory.fold_known(records)` and `envelope.history_of(records)`; `known_skills` / `behaviour_history` now delegate to them (same behaviour).
- States: integrity unchanged/changed/removed; behaviour empty/learning/healthy; overall warning > healthy (only when warmed up) > learning. A never-run skill is learning, not healthy.
- Wiring diff for Hamza's `board.py` tested in a throwaway worktree: full suite green, MCP lists hold no skill records on the demo store. Not committed: dashboard is his.
- `test_board_without_the_wiring_still_mislabels_skill_records` documents U1 and skips itself once `Board` has `skills`.

## 10. Scorer design note (2026-11-24)

- Branch `t16-scorer-design`, stacked on `t15-skills-board` (#21). Merge order #20, #21, then this. Document only: `docs/T16_SHARED_SCORER_DESIGN.md`.
- Prototype (scratchpad only, not committed): `live/proto_scorer.py` and `live/mcp_benign_replay.py` in the session scratchpad. It becomes `scripts/scorer_sweep.py` in the implementation PR. Data: 140 traced runs of word-count, csv-summary, notes-sync, dep-installer (`observe` is fast: about 0.08 s a run), and a 300-call MCP replay through `cim proxy`.
- Key numbers: 0 FP at z 2 to 6 over 690 scored benign observations; the A3-like extra destination, new binaries, private IP and a 3x result alert; +1 process and +60 bytes stay quiet; repeated attack: 1 alert today vs 5 with alerted runs kept out.
- Caveat written in the note: the corpus is deterministic, so the zero FP shows the gate works, not that z = 4 is calibrated for real skills (T-22 / T-28).
- Waiting on Hamza's six decisions (note section 11) before any code.

## 11. T-17 skills attacks A3 / A4 (2026-11-24)

- Branch `t17-skills-attacks`, stacked on `t16-scorer-design` (#22). Merge order #20, #21, #22, then this.
- A3: corpus skill `meeting-brief` (label suspicious). Lists action points; if the notes contain "quarterly", sends `{"env_names": [...], "decoy": ...}` to `--host/--port` (default 127.0.0.1:9). Names only, never values. Trigger input `corpora/skills/_attacks/t17-a3-trigger/notes-quarterly.md`, outside the skill, so hashes never change.
- A4: `corpora/skills/_attacks/t17-a4-update/word-count/` (SKILL.md + scripts/count.py v2, adds "longest line"); copied over the corpus COPY only.
- `_attacks/` has no SKILL.md, so `discover_skills` skips it and `corpus verify` is unaffected.
- `python -m cim.skills attack A3|A4 --work <empty dir>`: copies the corpus, baselines, 30 warm-up runs, attack step, sweep, one more run, checks. Exit 0 = PASS. On VM-MON add `--listener 10.10.10.30:<port>`.
- Seen: the helper's env as received has PWD and SHLVL besides clean_env's four (the scoped start gate runs through sh). Names only, harmless.
- Reliability: 10/10 each; prototype scorer 10/10 alerts on A3, 0/10 on A4.
- Detection is `attacks.novel_values` (never-seen check) until the scorer lands; then record_behaviour writes the alert and the attack report should read it from the store.

## 12. Docs stage: S2, threat model, cleanup (2026-11-24)

- Branch `t03-s2-threat-cleanup`, stacked on `t17-skills-attacks` (#23). Merge order #20 to #23, then this.
- ADR-006 (Proposed): record hash = SHA256(canonical_json(["cim-record/2", prev, artefact_id, type, name, origin, kind, ts, payload_text])); `store_meta.hash_version`; v1 stores verify but refuse appends; no migration. Callers to change: chain.py, baseline.py, canonical.py docstring, dashboard/call_demo.py tamper_log, three common tests.
- S2 repro: copy a store, `UPDATE record SET ts='1999…', artefact_id=2 WHERE id=10; UPDATE artefact SET name=…` → verify-chain ok, same tip, --expect-tip exit 0.
- Threat model v0.9 brought over unchanged in its own commit, then v0.10. Old branch `t03-threat-model` superseded; delete after merge.
- DECISIONS.md: added the missing ADR-005 row and ADR-006.
- Not touched: Hamza's progress files and `progress/milestones/dec-demo-2026.md`, which is also stale (says T-06 awaits review, VM-MON not booted); joint, flag to Hamza.

## 13. T-13 design note (2026-11-24)

- Branch `t13-pipeline-design`, stacked on `t03-s2-threat-cleanup` (#24). Merge order #20 to #24, then this.
- Key ideas: `cim.toml` (tomllib; precedence flag > env > file > default; loader refuses secret-looking keys); `cli.py` thin at the border, `cim.mcp.cli` and `cim.skills.cli` register their own commands; `cim skills ...` forwards to the argparse main; new `cim init`, `cim watch`, `cim status`, `cim events`, `cim skills exec`.
- Process model: watchdog supervises daemons (skills watcher, gateway) via exit + heartbeat files in `<store>.run/`; tracks wrappers (proxy, skills exec) via session files. Restarts recorded as `alert` `collector_restarted` under new artefact type `monitor` (v1.1).
- Status counts changed artefacts (drift writes one record per changed field).
- Throwaway check: `live/proto_supervisor.py` in the session scratchpad. Watcher -9, edit during gap, restart in 1.0 s, both edits recorded once.
- Limits written down: gap changes get the restart time; change-and-undo during a gap is invisible.

## 14. Contract 1.1.0 (2026-11-24)

- Fasih agreed all four drafted answers and asked to bundle everything. Branch `t02-contract-v1-1`, stacked on `t13-pipeline-design` (#25); merge order #20 to #25, then this. `t02-contract-fixes` (local) is now superseded: its two commits were cherry-picked.
- New: `common/schema/alerts.py` (ProxyAlertPayload, BehaviourAlertPayload + DriftFeature, MonitorAlertPayload, ALERT_PAYLOADS by code); `mcp.py` (behaviour response_bytes / session_id+seq / argument_shape_digest / value_classes with rules; McpSessionPayload, McpPinPayload, `record`; integrity `detail`; descriptor `tool_digest`); `envelope.py` (record dispatch, alert check by code and artefact type, artefact type `monitor` with `component`).
- Side effect for Hamza: his model dumps now include the new keys as null (and record "baseline"). All tests pass.
- Mutation check done: disabling the invocation_id rule or the alert id-match rule fails 4 tests.
- Also posted the PR summary on issue #19 (comment 7112318295) at Fasih's request.

## 15. Status check after #27 / #28 (2026-11-24)

- Hamza merged #20 to #26 (05:31 to 05:32 UTC), then #27 (his status docs) and #28 (H1 fix, U1 panels, ADR-006 accepted). He also edited three of my files sensibly: answered U1 in its doc, replaced the U1 "still mislabels" test with a real wiring test, and made `live_t16b_http.py` probe a check the refusal to start (and run on Windows).
- Re-checked on `d25ef41`: 355 passed; live scripts PASS; H1 closed (exit 2 at start without token); `/api/board` has `skills`; M2, M3, M5, L1 still reproduce.
- Updated on branch `t01-status-after-28`: CONTEXT (my section rewritten to current), ACTION, threat model v0.11 (H1 fixed, ADR-006 accepted, M5 re-tested), test report section 5, progress T-02/03/13/15/17.

## 16. T-11 boundary: ADR-007 (2026-11-24)

- Fasih asked for advice; options A (document), B (helpers as another user), C (monitor + store as their own `cim` user, root-owned launcher, `strace -u <operator>`), D (eBPF / audit). Recommended and saved: **A for FYP I, C for FYP II**, D only if T-33 needs tracer detection closed. B rejected: helpers lose the operator's files, so real skills break and AD2 changes meaning.
- Facts checked on this laptop: `user@1000.service` and its `cgroup.procs` owned by `fasih`; strace 7.3 has `-u`; `TracerPid` visible in `/proc/self/status`.
- Branch `t11-boundary-adr`, stacked on `t01-status-after-28` (#29). ADR-007, DECISIONS row, threat model v0.12 (6.2 wording, section 7 item 1), T-13 note decision 8 (one store writer; for December wrappers may still write directly through one function), T-11 progress, docstrings in `scoped.py` and `collector.py`.
- Hamza still has to agree T-13 decision 8.

## 17. Milestone + history refresh (2026-11-24)

- Fasih asked for two stale status files brought up to date, docs only. Branch `t01-milestone-history-refresh`, stacked on #30 (both #29 and #30 still open). PR `T-01: refresh December milestone and history entries`.
- **Milestone** (`progress/milestones/dec-demo-2026.md`, joint): C1 to C6 rewritten from the plan's own wording (section 2.1), each with what passes, the command or test, and what is open. Every command was re-run on a detached worktree of `org/main` @ `d25ef41` in the scratchpad: 355 passed / 0 skipped; `cim inventory` 150 tools; skills inventory 15; `cim sweep` on a doctored HexStrike list names `nmap_scan` description + `bcc`; both live scripts PASS; A3 PASS with 0 alerts on the board; `cim status` still the stub; M5 (Host: evil.example → 200) re-tested.
- Facts found on the way, written into the file, not decided: the plan's target is the week of 14 Dec, `PROJECT_STATUS.md` says ~1 Dec; T-07/09/12/14 reached `main` on 9 Nov through merge `d1af665` with no PR, and their task files still say IP; T-16b's file says "PR open"; there is no T-16 or T-18 task file; no test carries the `lab` marker; no demo script anywhere; the MCP attacks A1/A2 are not in the repo; the drift alert names what changed but not the old/new description text.
- **History**: 10 entries `history/entries/PR-00NN_T-XX.md` for #11–#13, #20–#26, using the org PR number (the older PR-0006/0007/0162/0163 files use pre-rebuild numbers). Each ends with a **Draft … Fasih to verify, then delete this line** marker. Not written: #10 (also Fasih's, no entry) and #29/#30 (still open).
- Left for Hamza in CONTEXT: items 6 (check milestone, target date, VM-MON) and 7 (his task files behind `main`).
- **Follow-up (same day, Fasih: "check the entries, add #10"):** added `PR-0010_T-01.md`; re-checked every entry claim against the merge diffs (`git diff <merge>^1 <merge>`), PR threads and code on `main`. Fixes: #22 sweep is **680** benign observations (4×110 + 2×120; PR #22 body and an old CONTEXT line said 690); #13 "tool_digest" line made exact (the `tool_digest()` function is the old digest; the 1.1 descriptor field is never filled); #10 evidence narrowed to what ACTION.md shows.
- **Real finding about my own #26:** the same HexStrike list gives manifest digest `f937f478…` at `3ad014b` (before #26) and `250070c7…` at `fa869ce` (after), because `tool_digest()` hashes `model_dump()`, which now holds `tool_digest: null`. Nothing compares stored digests today (drift uses `list_digest`). Recorded in the #26 entry and CONTEXT item 8; the fix is in Hamza's `inventory.py`, so it is his call.

## 18. MCP digest stability fix (2026-11-24)

- Fasih asked for the #26 digest shift to be fixed, after a plan he approved. Branch `t07-digest-stability`, stacked on #31. PR `T-07: keep MCP tool digests stable across contract 1.1`.
- `src/cim/mcp/inventory.py`: `DIGEST_FIELDS = {name, description, input_schema_digest}`; `_digest_view()` dumps only those; `tool_digest()` and the manifest digest both use it. Pre-1.1 values restored exactly (manifest `f937f478…`, `nmap_scan` `14557bed…`, computed on `3ad014b`).
- `tests/mcp/test_inventory.py`: `test_recorded_hexstrike_digests_do_not_move` (golden values on `corpora/mcp/tools_list.json`), `test_fields_added_to_the_descriptor_do_not_change_its_digest`. Both fail with the fix stashed, pass with it. 357 passed.
- Docs: `docs/CONTRACT_V1_1.md` section 1 correction; `history/entries/PR-0026_T-02.md` points at the fix; CONTEXT item 8 is now a review request.
- Not done: filling the 1.1 `tool_digest` field (Hamza's adoption). Skills side unaffected (#26 did not touch skills models; `corpus verify` pins tree digests). Stores written between #26 and this fix are not migrated.
- Hamza's territory (`src/cim/mcp/`, `tests/mcp/`): his to merge or decline.

## 19. `python -m cim.skills exec` (2026-11-24)

- Fasih asked for the skills twin of `cim proxy`. Branch `t11-skills-exec`, stacked on #32 (#29 to #32 still open). PR `T-11: python -m cim.skills exec (traced helper runs for an agent harness)`.
- `src/cim/skills/execute.py`: `find_skill` (ids as the inventory names them, `name#2` for a second copy), `resolve_script` (refuses absolute, any `..`, symlink out of the skill, missing, not `.py`/`.sh`), `store_behaviour` (the one store-writing function, ADR-007 / T-13 decision 8), `run` (refusals → tracer check → `observe` → record → output → exit).
- Exit codes: helper's own (128+N on signal N); 2 usage / no roots; 124 timeout; 125 no record (no systemd session, no strace, trace or store failure; stderr says whether the helper ran); 126 script refused; 127 unknown skill. Refusals happen before anything runs, and no store is created.
- Output: `runner.Captured` keeps each stream's first `MAX_OUTPUT_BYTES` (1 MB) as raw bytes plus the total size, on `RunResult.raw_stdout` / `raw_stderr`; text fields unchanged. `with_timeout_note` now works on `Captured`. stdout goes out byte for byte; exec's own lines (`exec: ...`, truncation, leaked processes, `-v` summary) go to stderr after the helper's. Output arrives after the helper ends (captured to files, not streamed); stdin is `/dev/null`.
- `inventory.installed_skills()` split out of `take_inventory()`, behaviour unchanged.
- Tests `tests/skills/test_skills_exec.py`: 19 (8 refusal cases, unknown skill, no roots, env roots, `name#2`, missing scope/tracer, signal mapping; live: record + exact bytes + args incl. `--`, signal + timeout, cap, failed store write). 376 passed; ruff, mypy, coverage 88%, sys tests clean.
- By hand on a fresh store (scratchpad): word-count, csv-summary, notes-sync (egress private_ip:9), cache-warmer (1 leaked process killed; spawn mkdir/sleep, writes ~ and ~/.config), meeting-brief benign (nothing), meeting-brief on `_attacks/t17-a3-trigger/notes-quarterly.md` (egress private_ip:9; with a loopback listener, env names + decoy received). `board`: 5 skills, 7 runs, 0 alerts (no scorer); chain ok (12 records). A first sweep after an exec run reports nothing for that skill.
- Not done (on purpose): `cli.py` mount (decision 5), scoring (on hold), session file under `<store>.run/sessions/` (watchdog PR).

## 20. Review of Hamza's #42 / #43 (2026-11-25)

- Hamza merged #29 to #33, then shipped #34 to #44 (contract 1.1 MCP writers, M1/M2/M3/M5/L1, ADR-006 hash v2, shared scorer #42, MCP wire #43). Ask note `docs/FASIH_ASK_2026-11-25.md`: review #42/#43, then skills call site, sweep, T-13 shared CLI.
- Local `t11-skills-exec` fast-forwarded to org `main` @ `8e1cf61`. Review on branch `t16-review-42-43` (CONTEXT + ACTION only). 400 passed, ruff and mypy clean.
- Parity OK: maths, floor, upward only, warm-up, top 3, composite, A1 `baseline`, chain-only inputs (M1), fault record (M4), payload.
- Findings posted in CONTEXT: (1) `score_latest` scores `rows[-1]`, not the record just written: two writers to one store → missed alert + duplicate (repro `repro_interleave.py` in a session scratchpad, not kept, alerts `[34, 34]`); fix = pass the `append_mcp` id. (2) outcome + A1: every error alerts forever (probe `probe2.py` in a session scratchpad, not kept: 5 of 5); suggest outcome-only alerts join the window. (3) test gaps. (4) double scoring + leftover comments in `score()`. (5) cost: 7/34/90 ms at 1k/5k/10k records, on the writer thread.
- Skills call site must score by the record id `store_behaviour()` returns (avoids finding 1).

## 21. Skills behaviour alerts (2026-11-25)

- Branch `t16-skills-alerts`, stacked on `t16-review-42-43`. PR `T-16: skills behaviour alerts`.
- `src/cim/skills/alert.py`: `SKILL_SCORER` (binaries, write_targets, destinations; processes, binaries_n, writes_n, destinations_n; window 100, warm-up 30), `observation_of`, `score_run(store, artefact_id, skill_id, record_id, ts)` scores the NAMED record against lower ids only, A1 via `skill_behaviour_drift` records' `observation_record_id`, no second alert for a record; `record_score_failure` → `skill_score_failed` (local `SkillScoreFailedPayload`).
- `inventory.append_event` returns the record id. `collector.record_behaviour` returns `Recorded(record_id, alert, score_error)` and fails open.
- `attacks`: `AttackReport.alert`; A3 passes only with an alert naming destinations; A4 only with none; render prints `behaviour alert:`. `exec` notes the alert on stderr (exit unchanged); `observe` prints it.
- Tests `tests/skills/test_skills_alert.py` (14) + live attack asserts. 414 passed; ruff, mypy clean. A3 10/10 alert, A4 0/10 (scratchpad runs). exec ×2 of the trigger → 2 alerts, chain ok.
- Not done: threshold sweep (next stage), profile still counts alerted runs (stated in T-15).

## 22. Threshold sweep (2026-11-25)

- Branch `t16-threshold-sweep`, stacked on `t16-skills-alerts`. PR `T-16: threshold sweep recorded`.
- `scripts/scorer_sweep.py`: skills series via `observe` on a `prepare`d copy (140 each of word-count, csv-summary, notes-sync, dep-installer); MCP series via a real `cim proxy` + `tests/mcp/sdk_server.py` (300 calls, seed 16, server logs to /dev/null), read back with `cim.mcp.alert._observations`; replay at z 2..6 with A1; 7 injected rows at z>=4 vs the full benign history; live `run_a3`/`run_a4`. Writes `docs/results/T16_threshold_sweep.md`; exit 1 on a benign alert at z>=4, an unexpected injected row or a failed attack. ~30 s.
- Result: 680 scored, 0 at z>=3; shout 4/120 at z>=2 (prototype said 0; noted in design section 8). Rerun identical except A3's random port.
- `tests/common/test_scorer_sweep.py` (4) covers `at_threshold`, `replay`, `inject`. 418 passed.

## 23. T-13 stage 1: config loader (2026-11-25)

- Hamza merged #45-#47, fixed findings 1-2 (#49), handover `docs/HAMZA_HANDOVER.md`. Local fast-forwarded to org main @ `46f28ad`; 421 passed; sweep smoke PASS.
- Branch `t13-config-loader` from main. PR `T-13: cim.toml config loader`.
- `src/cim/common/config.py`: pydantic frozen/strict/extra-forbid sections; `find_config`, `load_config` (applies CIM_SKILL_ROOTS), `read_config`, `parse_config`; `ConfigError` names file + dotted key; secret-named keys refused anywhere; paths relative to the file; `CimConfig.store_path` kept for the old test's callers; `server(id)`; `GatewayRouteSettings.root_name`.
- `cim.example.toml` (tracked template, defaults uncommented, MCP tables commented); tests check it equals defaults and that its commented tables load. `/cim.toml` gitignored.
- 27 config tests; 447 passed. Nothing wired yet (stage 2 = CLI restructure).
