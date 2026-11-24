# Threat model — Continuous Integrity Monitor

- **Status:** draft v0.11 for T-03. Written 2026-11-15 by Fasih (v0.9); v0.10 on 2026-11-24 (status per gap, test-report gaps); v0.11 the same day after PR #28 (H1 fixed, ADR-006 accepted; M5 and the other open rows re-tested). Not yet reviewed by Hamza, not signed off by the adviser.
- **Scope:** Phase 1 (SEE) as built, with pointers to where Phase 2 takes over.
- **What is different from a textbook model:** section 6 lists what the current code does not withstand, and for each gap whether it is fixed (and where) or still open. Each entry was reproduced and is recorded in `docs/HAMZA_REVIEW.md`, `docs/FASIH_MCP_TEST_REPORT.md` or the module it concerns, unless it says "from reading".

## 1. What CIM is for

An AI agent on a host is extended by two kinds of third-party content: **MCP servers**, which advertise tools the agent can call, and **skills**, which are directories of instructions plus helper scripts the agent can run. Both are approved once and trusted afterwards. CIM watches for the moment that trust stops being deserved: the content changes, or it starts behaving differently while looking the same.

## 2. Assets

| # | Asset | Why it matters |
|---|-------|----------------|
| AS1 | The monitored host: its files, credentials and network position | What an attacker ultimately wants |
| AS2 | The approved state of every tool and skill (baselines) | The reference everything is compared with |
| AS3 | The evidence store (hash-chained records) | Detection is only as trustworthy as its record |
| AS4 | The monitor itself: proxy, gateway, collectors, configuration | A blinded monitor reports that all is well |
| AS5 | Credentials that pass through CIM (MCP bearer tokens) | CIM sits in the path, so it can leak what it carries |
| AS6 | The operator's trust in what the dashboard says | A false "all clear", or a staged alert, defeats the purpose |

## 3. Who is trusted, and where trust ends

Trusted in Phase 1: the operating system kernel, the operator, the agent client (Cursor, or our harness), and CIM's own code on disk. Phase 2 attestation (T-26, T-27) removes the last of these from the trusted set.

| # | Boundary | Untrusted side | What stands on it |
|---|----------|----------------|-------------------|
| TB1 | Agent client ↔ MCP server (stdio or HTTP) | Everything the server sends | `cim proxy`, `cim http-gateway` |
| TB2 | Skill content ↔ host | Every file in a skill directory, and every process a helper starts | Skill runner, inventory, watcher, collector |
| TB3 | Monitor ↔ evidence store | Anything running as the monitor's user | The hash chain |
| TB4 | Operator's browser ↔ CIM's local HTTP ports | Any web page the operator has open | The dashboard and the gateway |
| TB5 | Host ↔ off-host verifier (Phase 2) | The whole host | Attestation |

TB2 and TB3 are weak today for one reason: helpers, the monitor and the store all belong to the same operating-system user. A boundary between processes of one user is a convention, not a control.

## 4. Adversaries

| # | Adversary | Can | Cannot (assumed) |
|---|-----------|-----|------------------|
| AD1 | Operator of an MCP server the agent uses | Change tool definitions at any time; return any bytes; behave differently for chosen inputs | Run code on the host except through what the agent does with its answers |
| AD2 | Author of a skill, or whoever can update it | Change any file in the skill; run code as the monitored user when a helper is invoked | Gain root |
| AD3 | Code already running as the monitored user (AD2 after first execution) | Read and write that user's files, including the store; signal that user's processes; move between that user's cgroups | Gain root; survive a reboot unseen once attestation exists |
| AD4 | A web page in the operator's browser | Send requests to `127.0.0.1` ports; with DNS rebinding, read the answers | Run code on the host directly |

Out of scope: a root or kernel-level attacker before Phase 2, a malicious agent client, attacks on CIM's dependencies, and denial of service against the host.

## 5. Attack matrix

The five rows required by the plan. "Detected by" names the task whose acceptance test covers the row.

| # | Attack | Adversary | What changes | Detected by | Phase |
|---|--------|-----------|--------------|-------------|-------|
| A1 | **MCP rug pull.** A server changes a tool's description or schema after approval | AD1 | The tool definition | T-07 pins the first `tools/list`; T-12 diffs every later one and records what moved | 1 |
| A2 | **MCP trigger tool.** A tool keeps its definition but acts differently on a chosen input | AD1 | Behaviour only; every hash is unchanged | T-09 captures each call; T-14 learns what calls look like; T-16 scores a new call against that | 1 |
| A3 | **Skills helper exfiltration.** A helper keeps its content but, on a trigger, reads something and sends it out | AD2 | Behaviour only; every hash is unchanged | T-11 records programs, file writes and connection attempts per invocation; T-15 profiles them; T-16 scores. Scripted as T-17 A3 (`meeting-brief`) | 1 |
| A3′ | The same, done by editing the helper | AD2 | File content | T-08 baselines every file; T-10 records the change within seconds | 1 |
| A4 | **Legitimate update.** A tool or skill changes for honest reasons | none | Content, sometimes behaviour | T-10 and T-12 still record the change; T-24 classifies it; T-31 re-baselines with provenance. Scripted as T-17 A4 (`word-count` update) | 1 records, 2 decides |
| A5 | **Monitor tampering.** The record is edited, a collector is stopped, or CIM's code is altered | AD3 | AS3, AS4 | T-06 hash chain for edits to the record; T-13 watchdog for a stopped collector; T-26 and T-27 for everything else | 1 partly, 2 fully |

Two attacks the plan does not name but the build must answer, because CIM introduces the surface itself:

| # | Attack | Adversary | Detected or prevented by |
|---|--------|-----------|--------------------------|
| A6 | **Evasion of attribution.** A helper leaves its cgroup, hides from sampling, or interferes with its tracer | AD2, AD3 | Sub-cgroups, instant exit and tracer kills are handled (T-05, T-11). Leaving the scope entirely is not: see 6.2 |
| A7 | **Abuse of CIM's own local services.** A web page or local process drives the dashboard or the gateway | AD4, AD3 | Nothing yet: see 6.4 |

### Every detection task traces to a row

| Task | Rows |
|------|------|
| T-07 MCP inventory, T-12 schema drift | A1, A4 |
| T-09 proxy, T-14 MCP envelope | A2 |
| T-08 skills inventory, T-10 integrity watcher | A3′, A4 |
| T-11 host collector, T-15 skills profile | A3, A6 |
| T-16 drift scorer | A2, A3 |
| T-06 store, T-13 watchdog | A5 |
| T-17 attack pack | A1, A2, A3, A4 (one scripted attack each) |
| T-19, T-20 scanners; T-23 trust score | A1, A3′ (static signs before behaviour) |
| T-24 correlation; T-31 update policy | A4 against A1 to A3 (telling an update from an attack) |
| T-26, T-27 attestation | A5 |
| T-29, T-30 response | A1 to A3 (acting on a detection) |

## 6. What the current build does not withstand

Short statements; the detail and the reproduction are in the place named. Review findings are in `docs/HAMZA_REVIEW.md` (letters and numbers such as D1), test-report findings in `docs/FASIH_MCP_TEST_REPORT.md` (H1, M1, L1 and so on). Status as of 2026-11-24, on `main` at `d25ef41` (after PR #28).

### 6.1 On TB1 (MCP server)

| Gap | Row | Status | Where |
|-----|-----|--------|-------|
| A malformed tool entry next to a rug pull stops the drift record being written | A1 | Fixed, PR #13 | D1 |
| Duplicate tool names, and changes to `title`, `annotations` or `outputSchema`, are not seen | A1 | Fixed, PR #13 | D2, D3 |
| Some frames stop the proxy forwarding at all | A2 | Proxy fixed, PR #12. Gateway: open as far as known (G4 was reproduced in the review; PR #16 does not list it as fixed; not retested) | P1, G4 |
| After one alert the unusual call is part of the baseline, so a repeated attack alerts once | A2 | Open. The scorer design keeps alerted runs out of the window | review A1; scorer design section 5 (PR #22) |
| Two sessions on one gateway route that reuse a request id lose a call from the record | A2 | Open | G6, M3 |
| A store write or scorer fault in the gateway, and a scorer fault in the proxy, leave no record | A2 | Open (from reading) | M4 |
| The gateway holds a streamed reply until it ends | (availability) | Open | G5, M2 |
| The proxy sees arguments and results, not what the server process does on its own host | A2 | By design | |

### 6.2 On TB2 (skills)

| Gap | Row | Status | Where |
|-----|-----|--------|-------|
| A helper can write a PID into a cgroup outside its scope; that process is then neither attributed nor killed | A6 | Open | `src/cim/skills/scoped.py` |
| A helper can tell it is traced and behave well; it can also tamper with a trace file it owns | A3, A6 | Open | `src/cim/skills/collector.py` |
| Helpers run with a clean environment, so the lab cannot show a helper stealing a real variable. The T-17 A3 stand-in sends variable names and a bundled decoy | A3 | By design | `corpora/skills/meeting-brief/` |
| Destinations are classed by address, never by name | A3 | Open | `collector.py` |

All four have the same root: the helper and the monitor are the same user. The fix is one decision that is still open: run helpers as a separate unprivileged user on VM-MON, or in a cgroup namespace, or record them through audit events.

### 6.3 On TB3 (evidence store)

| Gap | Row | Status | Where |
|-----|-----|--------|-------|
| `ts`, `artefact_id` and the whole `artefact` table are outside the hash: a record can be re-dated, moved to another tool, or its tool renamed, and the tip does not change | A5 | Open. Re-reproduced 2026-11-24. ADR-006 accepted (PR #28); the store code is still to come (T-06) | S2; `docs/decisions/ADR-006-record-hash-coverage.md` |
| Deleting the newest records, or rewriting the whole chain, leaves a valid chain | A5 | Mitigated, PR #11: `verify-chain` prints the tip and count, and `--expect-tip` / `--min-count` check them. Works only if the tip is kept off the host | S3 |
| Two writers break the chain without any attack | A5 (false alarm) | Fixed, PR #11 | S1 |
| The MCP observations the scorer reads are outside the chain: one `UPDATE` silences an alert while `verify-chain` passes | A2, A5 | Open. Reproduced 2026-11-23; the scorer design moves the inputs into the chained payload (contract v1.1) | E1, M1; scorer design section 6 |

The chain has no key and no anchor outside the host, so it proves consistency, not authenticity. That is acceptable for Phase 1 only if it is said out loud; T-27 is where an off-host party first holds something the host cannot rewrite.

### 6.4 On TB4 (CIM's own local services)

| Gap | Row | Status | Where |
|-----|-----|--------|-------|
| The dashboard has endpoints that wipe and rewrite the store, with no check on the caller | A5, A7 | Fixed, PR #16: off unless `--demo`, and then token, `Host` and `Origin` checked; `Origin: null` refused since PR #28. `--demo` on a real store can still clear it | X1 |
| The dashboard's read routes have no `Host` check: a DNS-rebinding page can read the board, and in `--demo` mode the page carries the token (writes stay refused) | A7 | Open (re-tested after PR #28: `GET /api/board` with `Host: evil.example` answers 200) | M5 |
| With no gateway token set (the documented setup), the gateway attaches stored bearer tokens to any local caller, including a web page sending `Origin: null` with a plain-text body | A7 | Fixed, PR #28: the gateway refuses to start when a route has `authorization_env` and no gateway token is set, and refuses `Origin: null` and non-JSON POSTs (checked: exits 2 at start) | G1, H1 |
| The gateway's path can leave the configured endpoint, and a redirect carries the token elsewhere | A7 | Fixed, PR #16. `%2e%2e` still reaches the upstream with the token (Low) | G2, G3, L1 |
| The demo alert on the board is written by the button, not by the detector | AS6 | Fixed, PR #16: the real scorer | X2 |

### 6.5 On the behaviour scorer (T-16, design in PR #22)

| Gap | Row | Status |
|-----|-----|--------|
| Warm-up learns whatever happens in the first 30 runs; a value seen then is never flagged later | A2, A3 | By design; calibration on a benign corpus (T-22) narrows it |
| A value that rises a little each run moves the mean with it ("boiling frog") | A2, A3 | Open; this is the T-33 slow-drift attack. A frozen second reference window is the usual answer |
| An attack that only uses programs, paths and destinations already seen is invisible to the categorical features | A2, A3 | Open; T-33 mimicry |
| Numeric features are scored upward only, so doing less never alerts | A2, A3 | By design |

## 7. What to settle before December

1. The same-user boundary for skills (6.2). It decides how much of A3 and A6 the demo can honestly claim.
2. What the store hash covers (S2): ADR-006 is accepted; the store code must land before either side keeps a store.
3. The gateway is part of the December build (ADR-005), and the demo buttons sit behind `--demo` (PR #16). H1 is fixed (PR #28). M5 must be fixed before the board is shown on a network-connected machine.
4. The scorer's inputs move into the chain (M1) before the C4 demo claims that a behaviour record cannot be edited unseen.
5. The wording of the claim for A5 in Phase 1. Today: "edits to recorded payloads are detected", not "the record cannot be tampered with". After ADR-006: "edits to recorded payloads, dates and attribution are detected; a rebuilt chain is detected only against a tip kept off the host".
