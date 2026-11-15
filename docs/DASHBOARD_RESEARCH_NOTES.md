# Dashboard research notes — answer to `docs/FASIH_DASHBOARD_RESEARCH.md`

- **Status:** draft recommendation, 2026-11-15, Fasih. Research only: nothing here is implemented, and nothing here asks for MCP proxy or gateway changes.
- **Brief:** Hamza's three questions of 12 Nov (form factor, sections, auto-disconnect). The brief itself is on `t16-alerts-http-dashboard`.

## Summary

1. **Form factor:** keep one local board for December, make it strictly read-only, and build the FYP II operator surface as a local web app served by CIM. No public website is needed for either gate.
2. **Sections:** eight, listed in section 2. Five are shared, two are MCP-only, one is skills-only. The skills data for all of them already exists on the skills branches.
3. **Auto-disconnect:** a five-state ladder per tool or skill. In FYP I it is display only. In FYP II soft steps are automatic and hard steps need the operator, and every step is a record in the hash chain.

## 1. Form factor

| Option | For | Against | Verdict |
|--------|-----|---------|---------|
| Local board (today) | Already works; no auth to design; evidence never leaves the host | One store, one viewer; today it also has write endpoints (`HAMZA_REVIEW.md` X1) | **FYP I**, once read-only |
| Local web app served by CIM | Same trust position as the board; room for evidence drill-down and operator actions; needs only a per-run token | Needs a read API and an action API with a contract | **FYP II** |
| Hosted web app with accounts | Multi-operator, remote access | Moves evidence and tokens off the host; needs real auth, hosting and a privacy story; none of it is graded | Not recommended |
| Website | Tells the project story | Not a monitor; no criterion asks for it | Optional, after April, static only |

Why local in both phases: CIM has one operator and one monitored host, the evidence is sensitive, and Phase 2 already adds the only remote party that matters, the off-host verifier (T-27). A hosted app would add a second remote party with none of the verifier's guarantees.

**What must exist for December (C1 to C6):** the current board, read-only, showing chain status, inventory counts, schema changes, calls and alerts. C5 asks for `cim status`, not for a UI, so the board is supporting material and the CLI is the graded surface.

**What waits for FYP II (T-34):** operator actions, trust scores, attestation status, evidence export.

**What Hamza would need to expose for the FYP II app:**
- A read API with a stable JSON shape per record kind, built on the contract (not on raw payloads).
- Incremental reads: "records after id N". The board today re-reads and re-verifies the whole store every 2 s (U2).
- A per-run token, plus `Origin` and `Host` checks, on every route. Read routes included: the records are sensitive.
- A separate action API (section 3). Nothing that changes state should share a route with a read.

**What I own in that UI:** the skills read model and the three skills views (inventory, integrity events, behaviour profile). The functions exist: `known_skills`, `behaviour_history`, `profiles` in `cim.skills`.

One thing to fix whichever option we take: the board currently shows a skill integrity record as an MCP schema change and a skill behaviour record as a call to tool `unknown` (U1).

## 2. Sections of the final dashboard

States used below, the same five everywhere so the operator learns them once:

| State | Meaning |
|-------|---------|
| Empty | Nothing recorded yet |
| Learning | Recorded, but fewer than 30 observations: no behaviour judgement is possible |
| Healthy | Enough observations, nothing open |
| Warning | An alert or an unreviewed change is open |
| Disconnected | Paused or quarantined (FYP II), or the collector for it is not running |

| # | Section | Purpose | Data source | Updates | Operator actions | Side |
|---|---------|---------|-------------|---------|------------------|------|
| 1 | Record integrity | Say whether the evidence itself can be believed | `verify_chain`; record count and tip hash; from FYP II the verifier's last verdict | On load and after each new record; full re-verify on demand | Verify now; copy tip hash; export | Shared |
| 2 | MCP servers and tools | Show what is bound and what each tool looked like when approved | `artefact` records for `mcp_server` and `mcp_tool` | When a `tools/list` is seen | Open a tool's approved definition | MCP |
| 3 | Skills | Show what is installed and whether each still matches its baseline | `artefact` records for `skill`, folded with later `integrity` records | When the watcher records a change (seconds) | Open a skill's file list with hashes | Skills |
| 4 | Changes | Every change to an approved tool or skill, newest first | `integrity` records, both sides | On each new record | Mark reviewed; from FYP II accept as update (re-baseline) or reject (rollback) | Shared |
| 5 | Behaviour | What normal looks like, and what just left it | MCP: envelope and `behaviour` records. Skills: `behaviour` records and `profiles` | On each call or invocation | Open the profile; open the alert | Shared |
| 6 | Alerts | One list of everything that needs a decision | `alert` records | Push or short poll; this is the one section that must be prompt | Acknowledge; open evidence | Shared |
| 7 | Evidence drawer | For one alert or change: the records behind it, in order, with their chain position | The records themselves, by id | On open | Copy record ids and hashes; export this case | Shared |
| 8 | Connection and collectors | Which proxies, gateways and watchers are running, and what is paused or quarantined | Process state from T-13's watchdog; response records (section 3) | Poll | From FYP II: pause, quarantine, release | Shared |

What each state means per section, where it is not obvious:

- **Record integrity** has no Learning state. Warning means the chain is broken, and it should take over the page: nothing else on the board can be trusted until it is explained.
- **Skills** has no Learning state for integrity (a hash either matches or it does not) but does for behaviour.
- **Behaviour** in Learning must say so in words and show the count ("12 of 30"). A quiet board during warm-up must not read as a clean bill of health.
- **Alerts** Empty and Healthy look the same; say "no open alerts" and when the last one was closed.

Needed for December beyond what exists: section 3 in a minimal form (count of skills, count of changed files), so C1's "every installed skill" is on screen next to the tools. Everything else in the table can be the existing board.

Not recommended for the board: a "clear" control and a "tamper" control. A demo reset belongs in a separate command that only works on a store it created.

## 3. Auto-disconnect of skills and MCP

### Ladder

Per tool, per MCP server, or per skill:

```
Learning ──▶ Healthy ──▶ Warning ──▶ Paused ──▶ Quarantined
                ▲            │           │            │
                └────────────┴───────────┴── release ─┘   (operator; returns to Learning)
```

| State | What CIM does | Who moves it on |
|-------|---------------|-----------------|
| Learning | Records; never blocks | CIM, at 30 observations |
| Healthy | Records | CIM, on an alert |
| Warning | Records; shows the alert | CIM to Paused on the triggers below, or the operator either way |
| Paused (soft) | MCP: the proxy refuses calls to that one tool. Skills: the runner refuses that one skill. Nothing is removed | Operator: release or quarantine. CIM: quarantine if it happens again while paused |
| Quarantined (hard) | MCP: the tool is refused and removed from the advertised list, or the whole server session is dropped. Skills: the skill directory is moved out of the skill roots and its baseline kept | Operator only |

### Triggers

| Trigger | Step |
|---------|------|
| Behaviour alert, first time | Healthy → Warning |
| Behaviour alert again within the window, or a correlation verdict of "trigger-activated compromise" (T-24) | Warning → Paused, automatic |
| Integrity change with no provenance (not a known update) | Warning; Paused if a helper script or a tool description changed |
| Integrity change plus a scanner finding (T-19, T-20), or a verdict of "malicious-update candidate" | Paused, automatic; Quarantined needs the operator |
| Chain broken, or a collector killed and not restarted | No tool is blocked for this; the whole board goes to Warning. Blocking on a broken record would let an attacker switch tools off by damaging the store |

Soft steps are automatic because they are cheap to undo and an agent session keeps working without one tool. Hard steps need the operator, at least for the first version: a false quarantine of a server in the middle of work is the outcome most likely to get the monitor switched off.

A release always returns to Learning, not to Healthy: after a pause the old baseline is suspect, and after an accepted update it is out of date.

### How it is recorded

Every step is a record in the hash chain, written before the step takes effect:

- which artefact, from which state to which state;
- what caused it (the alert or verdict record id), or which operator action;
- for a release: whether the baseline was kept, or replaced by an accepted update.

The contract has no kind for this today. Options: a new kind `response`, or `alert` records with reserved codes. I prefer a new kind, because a release is not an alert, and it should go into the same contract revision as the v1.1 items.

Reconnect is an operator action in the app (or `cim` CLI), never automatic, and never by editing a file. The dashboard's current "connected" flag is a `.session` file next to the store; in FYP II the state has to come from the chain.

### Wording per state

| State | Shown as | One line under it |
|-------|----------|-------------------|
| Learning | Learning | "12 of 30 uses seen. Not judged yet." |
| Healthy | Normal | "Matches its approved version and its usual behaviour." |
| Warning | Needs a look | "Did something it has not done before." / "Changed since it was approved." |
| Paused | Paused by CIM | "Calls to this tool are refused until you decide. Nothing was removed." |
| Quarantined | Quarantined | "Removed from use on <date> by <operator or rule>. Its approved version is kept." |

### FYP I and FYP II

| | FYP I (December) | FYP II (T-29, T-30) |
|---|---|---|
| States shown | Learning, Healthy, Warning | All five |
| Blocking | None. Observe only | Paused automatic, Quarantined by operator |
| Recorded | Alerts | Alerts and every state change |
| Reconnect | Not applicable | Operator action, recorded |
| Hook | The `allow_call` stub in the proxy; nothing on the skills side | Proxy and gateway refuse; runner refuses; skill directory moved |

For December the board should not show "disconnected" at all unless something really was refused. Showing it for a staged step would claim a capability that is scheduled for March.

## Open questions for Hamza

1. Is the HTTP gateway part of the December build? It changes who can reach CIM (TB4 in the threat model draft) and so what the board has to defend.
2. New record kind `response`, or reserved alert codes?
3. For MCP, is the unit of quarantine the tool or the server? The plan says tool (refused and removed from the list); a dropped session is simpler to build and blunter.
