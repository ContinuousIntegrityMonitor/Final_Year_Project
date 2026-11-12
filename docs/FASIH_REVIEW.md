# Fasih review handoff — read this first (Claude / human)

Paste into Claude: *You are assisting Fasih on CIM. Read `docs/FASIH_REVIEW.md`, then `CONTEXT.md`, `DECISIONS.md`, `PROJECT_STATUS.md`, and this PR’s diff. Review only joint / border items listed below. Do not merge without Fasih’s explicit OK. Do not invent Hamza-side MCP work.*

---

## Remotes (both must stay in sync)

| Remote | URL |
|--------|-----|
| `origin` (day-to-day + PRs) | https://github.com/HamzaFarooq3333/Final_Year_Project |
| `org` (committee home) | https://github.com/ContinuousIntegrityMonitor/Final_Year_Project |

After review comments, Hamza dual-pushes. Same CI workflows on both (`ci-push`, `merge-gate`).

---

## Working rules (do not weaken)

1. **Territory:** `src/cim/mcp/` = Hamza sole; `src/cim/skills/` = Fasih sole; `src/cim/common/**` = border (both review).
2. **CODEOWNERS** matches that split (`/src/cim/common/schema/` both; store is under `common/` → joint).
3. **Branches:** `tXX-slug`; PR title `T-XX: …`; no force-push to `main`.
4. **No Cursor / AI co-author trailers** on commits.
5. **Progress truth:** `progress/tasks/T-XX.md`. History interpretation: `history/entries/`.
6. **T-06 must not merge to `main` until Fasih reviews and approves** (even if CI is green).
7. **FYP I (ADR-003):** functional MCP SEE path by ~1 Dec; product polish deferred to FYP II.
8. Stacked Hamza work (T-07+) may live on branches that include T-06 **without** merging #163 early.

---

## What to review now (JOINT — your action)

### Priority 1 — T-06 baseline store (one review, then say if anything should change)

Please review this once. Reply on the PR with either "ok" or the specific improvements you want. Hamza is not blocked on it: T-12 and T-14 are stacked on top, and a requested change gets folded back into the store before merge.

- **Org PR:** https://github.com/ContinuousIntegrityMonitor/Final_Year_Project/pull/1 — open, no review and no comment as of 2026-11-09. GitHub would not assign `fasih-moin` because he is not a collaborator on that repo.
- **Personal PR (older history):** https://github.com/HamzaFarooq3333/Final_Year_Project/pull/163
- **Owner:** impl Hamza, **review Fasih** (plan: joint design, H implements, F reviews)

The store gained one read-only method, `read_records()`, so the rug-pull detector can see the pin. There is still no update or delete path.

**Files to inspect**

| Path | Why |
|------|-----|
| `src/cim/common/store/baseline.py` | Append-only SQLite WAL API |
| `src/cim/common/chain.py` | `record_hash = SHA256(prev \|\| kind \|\| canonical_json)` |
| `src/cim/cli.py` (`verify-chain`) | CLI surface both sides will use |
| `tests/common/test_store.py` | Acceptance evidence |
| `progress/tasks/T-06.md` | Status checklist |

**Review checklist (pass/fail)**

- [ ] No update/delete API or DDL path for mutating historical rows
- [ ] Tamper (edit or delete row) fails `verify_chain` with a clear `broken_at`
- [ ] Genesis prev-hash is 64 zero hex digits; payloads use `canonical_json` (no floats)
- [ ] 10k appends under 5s test is honest (same process, real inserts)
- [ ] Skills-side can reuse this store later for T-08 without schema surprises
- [ ] CLI `cim verify-chain --db` exit codes: 0 ok / 1 broken

**If approved:** comment approve on #163; Hamza merges (or you merge) to `main`, then dual-push.  
**If changes needed:** comment concrete diffs; Hamza fixes on the same branch.

### Priority 2 — Contract / schema border (already on `main`)

Only re-open if T-06 or T-07 forces a schema change:

- `src/cim/common/schema/mcp.py` — `McpArtefactPayload`, digests
- `src/cim/common/schema/canonical.py` — hashing rules
- Any new fields required by inventory/proxy → **both must review** before merge

#### Request from Hamza: contract v1.1 for proxy capture (T-09)

T-09 currently stores each `tools/call` as `McpBehaviourPayload` (v1.0). Three things the plan asks
the proxy to log have no field today, so they are not stored:

| Need (plan T-09) | Proposed change | Why |
|---|---|---|
| Response size | `response_size: StrictInt >= 0` on `McpBehaviourPayload` (optional) | SYS-03 evidence, T-14 envelope feature |
| JSON-RPC method + order | `method: Literal["tools/call"]`, keep order in `invocation_id` (`000042:<id>`) | Make order explicit without parsing ids |
| `initialize` exchange | New `McpSessionPayload` (server name/version, protocol version, capabilities digest) under kind `artefact` for `mcp_server` | C2 shows which server build the session talked to |
| Proxy alerts | `ProxyAlertPayload` (code, direction, reason, sha256, size) for kind `alert` | Alerts are unvalidated today |

Checklist for you: accept / change / reject each row. Hamza will not edit `common/schema/` until you agree.

### Priority 3 — Your sole path (not blocking T-06 merge)

| Task | Status | Your next |
|------|--------|-----------|
| T-05 skills lab / corpus | IP (skeleton PR #6 on main) | Finish runner + corpus acceptance |
| T-08 skills artefact inventory | Blocked on T-06 (+ T-05) | After #163 merges, mirror T-07 pattern for skills |
| T-10 / T-11 | Later | After T-08 |
| Final dashboard research | **New 12 Nov 2026** | Read [`docs/FASIH_DASHBOARD_RESEARCH.md`](FASIH_DASHBOARD_RESEARCH.md): form factor, section IA, auto-disconnect (skills + MCP). Research only — do not build UI or quarantine yet. |

---

## What Hamza is doing in parallel (NOT waiting on merge)

Per ADR-003 / critical path: **T-07 MCP artefact inventory** (then **T-09 proxy**) stacked on the T-06 branch so Dec C1–C2 can move while you review.

| Task | Territory | Branch / PR | Needs your review? |
|------|-----------|-------------|--------------------|
| T-07 MCP inventory | Hamza sole (`src/cim/mcp/`) | `t07-mcp-inventory` (stacked on T-06) | Only if it changes `common/schema` or `common/store` API — it should not |
| T-09 MCP proxy | Hamza sole | `t09-mcp-proxy` (stacked on T-07) | No `common/` edits; see contract v1.1 request above |
| T-12 rug-pull | Hamza sole | `t12-mcp-drift` | No. Reads the store; does not change the schema |
| T-14 envelope | Hamza sole | `t14-mcp-envelope` | No. Observations sit in `envelope_obs`, outside the hash chain |
| Status board | Hamza leads | `t14-status-board` | No. Read-only page. It does not change the schema |

**T-07 touch list (Hamza sole — optional skim):** `src/cim/mcp/inventory.py`, `tests/mcp/test_inventory.py`, `cim inventory` CLI, `corpora/mcp/servers.json`. Uses existing `BaselineStore` + `McpArtefactPayload` without widening the store API.

You do **not** need to approve T-07/T-09 implementation detail in `mcp/` before T-06 lands. Glance at PRs for accidental `common/` edits.

---

## FYP I December bar (shared)

Must show MCP SEE path: **T-04 lab → T-06 store → T-07 inventory / T-09 capture** toward C1–C5.  
Skills half (T-08+) strengthens C1/C4 but polish and full behavioural path can trail if needed (ADR-003).

Org identity: `fyp26_cim@gmail.com` / ContinuousIntegrityMonitor.

---

## Suggested Claude review prompt (T-06)

```
Review PR #163 (t06-baseline-store) as Fasih for CIM.
Read docs/FASIH_REVIEW.md Priority 1 checklist.
Focus on common/store and common/chain only.
Report: approve / request changes, with file:line notes.
Do not redesign MCP inventory or proxy.
```
