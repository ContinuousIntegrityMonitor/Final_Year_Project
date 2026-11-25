# Hamza handover — read this first (Claude / Cursor)

Paste into Claude or Cursor:

*You are assisting Hamza Farooq on CIM (MCP lead). Read `docs/HAMZA_HANDOVER.md` first, then `CONTEXT.md` (Hamza’s assistant section), `ACTION.md`, `PROJECT_STATUS.md`, `docs/FASIH_ASK_2026-11-25.md`, and Fasih’s review notes in `CONTEXT.md` under Fasih’s section (findings on #42/#43). Follow territory and git rules. Do not invent Fasih skills work. Do not use `git commit` from the agent — ship with `scripts/_ship.sh` / commit-tree only. No Cursor/AI co-author trailers. Author: HamzaFarooq3333 / hamzafarooqsea@gmail.com.*

**Handover date:** 2026-11-25  
**Org `main` tip:** `7c0bc6f` (PR #49 — findings 1–2 fixed; includes #45–#48)  
**Remotes:** `org` = ContinuousIntegrityMonitor/Final_Year_Project (committee); `origin` = HamzaFarooq3333/Final_Year_Project (may diverge — prefer `org`).

---

## Hard rules (never weaken)

1. **Territory:** `src/cim/mcp/` + dashboard MCP bits = Hamza; `src/cim/skills/` = Fasih; `src/cim/common/**` = border (both review).
2. **Ship:** `scripts/_ship.sh` → CI green → PR → merge. Never `git commit` from the agent (Cursor injects co-author). Never force-push `main`.
3. **Status truth:** after each ship/merge, append `ACTION.md`, rewrite Hamza’s section + Active-now in `CONTEXT.md`, refresh `PROJECT_STATUS.md`.
4. **Phase:** FYP I / ADR-003 — functional SEE path for Dec demo (week of 14 Dec). No FYP II quarantine/attestation unless asked.
5. Treat Roma / chat memory as secondary to these files.

---

## What just landed (do not redo)

| PR | What |
|----|------|
| #42 | `cim.common.scorer` (Hamza) |
| #43 | MCP `score_latest` → shared scorer (Hamza) |
| #44 | Ask Fasih (`docs/FASIH_ASK_2026-11-25.md`) |
| **#45** | Fasih review of #42/#43 in CONTEXT |
| **#46** | Skills behaviour alerts (`cim.skills.alert`) |
| **#47** | Threshold sweep `scripts/scorer_sweep.py` + `docs/results/T16_threshold_sweep.md` |
| **#49** | Findings 1–2: score by `observation_record_id`; outcome-only joins window |

Skills C4 path is now coded: A3 writes `skill_behaviour_drift`. MCP stand-in alerts already work via shared scorer. Findings 1–2 are fixed.

---

## Your next work (priority order)

### 1. Findings 1–2 — **done (#49)**

Do not re-implement. `score_latest` requires `observation_record_id`; proxy passes `append_mcp`’s return. A1 excludes only alerts that drifted on `argument_shape` / `value_class` / `result_size`.

### 2. Optional tidy (findings 3–5) — low priority

Missing MCP parity tests (argument shape, first error, result size); scorer double-loop clean-up; store parse cost. Can wait or small follow-up PR.

### 3. After Fasih lands T-13 shared CLI — **your decision‑7 pieces**

Green-lit T-13 §10 decision **7** (Hamza):

- `--config` handling in proxy and gateway  
- MCP status summary / event descriptions  
- Gateway heartbeat file  
- Proxy session file  

Do **not** invent the whole CLI; wait for his structure (`cim status`, two-sided inventory, etc.).

### 4. Live demo (with Fasih)

Preferably after T-13 stub usable: run live MCP + skills through CIM, confirm alerts + dashboard + `verify-chain`. No quarantine. Scripts: `scripts/live_t16_stdio.py`, `scripts/live_t16b_http.py` (Unix venv paths; on Windows use `.venv/Scripts/`).

### 5. Still open for Dec demo C1–C6

| Criterion | Gap |
|-----------|-----|
| C1 | Single `cim inventory` needs T-13; VM-MON inventory not done |
| C2 | No live HexStrike on VM-MON |
| C3 | No live rug-pull on VM-MON; MCP attack pack A1/A2 not in repo (Hamza T-17) |
| C4 | Stand-in + skills alerts OK; no HexStrike trigger |
| C5 | `cim status` awaits T-13 |
| C6 | Demo script + advisor video not started |

Rough progress: **~80% code building blocks**; **~55–60% live Dec criteria** until T-13 + lab + video.

### 6. Do **not** start unless asked

- Docker Desktop / containerized test harness (not a Phase 1 deliverable; Engine+CLI is T-01 tooling only)  
- FYP II: T-29 quarantine, attestation  
- Rewriting Fasih skills code  

---

## Fasih is doing next

- T-13 shared CLI (config loader, restructure, `cim status` / `events` / `watch`, two-sided inventory/sweep/envelope)  
- He asked you to merge #45→#46→#47 (**done** 2026-11-25)  
- Findings 1–2: Hamza fixed in **#49** (answered in CONTEXT)

---

## How to ship (Windows)

```text
D:\Git\Git\bin\bash.exe scripts/_ship.sh <local-branch> <remote-branch> scripts/_msg.txt <paths...>
```

Gates must pass; wait for `CI success`; open PR with `gh`; merge when green. Verify `git log -1 --format=%B` has no `Co-authored-by: Cursor`.

---

## Files to open first when starting a task

1. This file  
2. `CONTEXT.md` → Fasih findings + Hamza “What I am about to do”  
3. `docs/T16_SHARED_SCORER_DESIGN.md` §5–7 (for finding 1)  
4. `docs/T13_PIPELINE_DESIGN.md` §10 (for later decision 7)  
5. `src/cim/mcp/alert.py`, `src/cim/mcp/proxy.py`  

Roma (optional): FYP-31–34 on Final Year Project list; keep current when status changes.
