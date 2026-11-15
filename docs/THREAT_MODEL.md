# Threat model — Continuous Integrity Monitor

- **Status:** draft v0.9 for T-03, written 2026-11-15 by Fasih. Not yet reviewed by Hamza, not signed off by the adviser.
- **Scope:** Phase 1 (SEE) as built, with pointers to where Phase 2 takes over.
- **What is different from a textbook model:** section 6 lists what the current code does not withstand. Each entry was reproduced and is recorded in `docs/HAMZA_REVIEW.md` or in the module it concerns.

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
| A3 | **Skills helper exfiltration.** A helper keeps its content but, on a trigger, reads something and sends it out | AD2 | Behaviour only; every hash is unchanged | T-11 records programs, file writes and connection attempts per invocation; T-15 profiles them; T-16 scores | 1 |
| A3′ | The same, done by editing the helper | AD2 | File content | T-08 baselines every file; T-10 records the change within seconds | 1 |
| A4 | **Legitimate update.** A tool or skill changes for honest reasons | none | Content, sometimes behaviour | T-10 and T-12 still record the change; T-24 classifies it; T-31 re-baselines with provenance | 1 records, 2 decides |
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

Short statements; the detail and the reproduction are in the place named.

### 6.1 On TB1 (MCP server)

| Gap | Row | Where |
|-----|-----|-------|
| A malformed tool entry next to a rug pull stops the drift record being written | A1 | `HAMZA_REVIEW.md` D1 |
| Duplicate tool names, and changes to `title`, `annotations` or `outputSchema`, are not seen | A1 | D2, D3 |
| Some frames stop the proxy forwarding at all | A2 | P1, G4 |
| After one alert the unusual call is part of the baseline; a tool that misbehaves from its first call never alerts | A2 | A1 in section 5 of the review |
| The proxy sees arguments and results, not what the server process does on its own host | A2 | by design |

### 6.2 On TB2 (skills)

| Gap | Row | Where |
|-----|-----|-------|
| A helper can write a PID into a cgroup outside its scope; that process is then neither attributed nor killed | A6 | `src/cim/skills/scoped.py` |
| A helper can tell it is traced and behave well; it can also tamper with a trace file it owns | A3, A6 | `src/cim/skills/collector.py` |
| Helpers run with a clean environment, so the lab cannot yet show a helper stealing a real variable; the corpus uses a bundled decoy | A3 | `corpora/skills/MANIFEST.json` |
| Destinations are classed by address, never by name | A3 | `collector.py` |

All four have the same root: the helper and the monitor are the same user. The fix is one decision that is still open: run helpers as a separate unprivileged user on VM-MON, or in a cgroup namespace, or record them through audit events.

### 6.3 On TB3 (evidence store)

| Gap | Row | Where |
|-----|-----|-------|
| `ts`, `artefact_id` and the whole `artefact` table are outside the hash: a record can be re-dated or moved to another tool | A5 | S2 |
| Deleting the newest records, or rewriting the whole chain, leaves a valid chain | A5 | S3 |
| Two writers break the chain without any attack | A5 (false alarm) | S1 |
| MCP call observations used for scoring are kept outside the chain | A2, A5 | E1 |

The chain has no key and no anchor outside the host, so it proves consistency, not authenticity. That is acceptable for Phase 1 only if it is said out loud; T-27 is where an off-host party first holds something the host cannot rewrite.

### 6.4 On TB4 (CIM's own local services)

| Gap | Row | Where |
|-----|-----|-------|
| The dashboard has endpoints that wipe and rewrite the store, with no check on the caller | A5, A7 | X1 |
| The gateway attaches stored bearer tokens to any request that reaches it | A7 | G1 |
| The gateway's path can leave the configured endpoint, and a redirect carries the token elsewhere | A7 | G2, G3 |
| The demo alert on the board is written by the button, not by the detector | AS6 | X2 |

## 7. What to settle before December

1. The same-user boundary for skills (6.2). It decides how much of A3 and A6 the demo can honestly claim.
2. What the store hash covers (S2), before either side keeps a store.
3. Whether the gateway and the demo buttons are part of the December build at all. If they are, G1 to G3 and X1 need fixing first; if not, they should not be reachable from `cim dashboard`.
4. The wording of the claim for A5 in Phase 1: "edits to recorded payloads are detected", not "the record cannot be tampered with".
