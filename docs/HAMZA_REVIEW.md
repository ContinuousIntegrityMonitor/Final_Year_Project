# Review notes for Hamza — whole-project pass

- **From:** Fasih · **Date:** 2026-11-15 · **Code reviewed:** branch `t05-cgroup-invocation` at `9db7095` (includes T-06, T-07, T-09, T-12, T-14 and the status board)
- **What I changed:** only my own territory (`src/cim/skills/`, `tests/skills/`, `corpora/skills/`), on separate branches (section 4). Nothing under `src/cim/mcp/`, `src/cim/dashboard/`, `src/cim/common/store/`, `scripts/` or `corpora/mcp/` was edited. Three schema fixes are on a local branch waiting for your agreement (section 3).
- **How to read this:** every item below was reproduced on the code as it stands, not inferred from reading. Each has the file and line, what happens, and a suggested fix. Fix order is the order listed.

The suite is green (`pytest`, `ruff`, `mypy`). None of these are caught by the current tests.

## At a glance

| # | Area | Problem | Severity |
|---|------|---------|----------|
| P1 | Proxy | Certain frames make the proxy stop forwarding (breaks ADR-004 fail-open) | High |
| D1 | Drift | A server can switch drift detection off with one malformed tool entry | High |
| D2 | Drift | Duplicate tool names hide a changed tool | High |
| D3 | Drift | `title`, `annotations`, `outputSchema` changes are invisible | High |
| S1 | Store | Two writers on one store break the chain (false "tampered") | High |
| S2 | Store | `ts`, `artefact_id` and the `artefact` table can be edited without breaking the chain | High |
| C1 | CLI | `cim inventory` then `cim sweep` reports "no pin" | Medium |
| P2 | Proxy | `cim proxy` hangs forever if the server command cannot start | Medium |
| D4 | Drift | The same drift is recorded again on every re-read | Medium |
| D5 | Drift | A paginated `tools/list` is read as tools being removed and added | Medium |
| P3 | Proxy | New artefact rows every session; `invocation_id` repeats across sessions | Medium |
| P4 | Contract | The pin record and drift records do not fit the T-02 contract | Medium |
| S3 | Store | Deleting the newest records is not detected | Medium |
| E1 | Envelope | Reading the envelope writes to the store; a connection is opened per call | Low |
| U1 | Dashboard | Skill records are shown as MCP schema changes and tool calls | Medium |
| U2 | Dashboard | Full chain verify and full record read every 2 s per open tab | Low |
| I1 | Inventory | A float and its string form hash the same | Low |
| P5 | Proxy | JSON-RPC batch frames are flagged malformed and their calls are not captured | Low |
| S4–S6 | Store | Smaller notes (timestamp check, artefact lookup, the 10k test) | Low |

---

## 1. MCP territory (`src/cim/mcp/`, `cli.py`, dashboard)

### P1 — Some frames stop the proxy forwarding (High)

ADR-004 says capture never alters forwarding. Three inputs break that, because capture runs inline in the forwarding loops and only `UnicodeDecodeError`/`ValueError` from parsing are caught (`proxy.py:197`).

| Input | Who controls it | What happens |
|-------|-----------------|--------------|
| `tools/call` result (or arguments) containing a lone surrogate escape such as `"\ud800"` | Server (or client) | `digest()` (`proxy.py:101`) raises `UnicodeEncodeError` inside `capture.server_line` (`proxy.py:395`). `run_proxy` raises; later server replies are never forwarded. |
| A server line with very deep nesting (`[[[[…`, about 200k levels) | Server | `json.loads` raises `RecursionError`, which is not a `ValueError`. Same result. |
| A client line with very deep nesting | Client | `capture.client_line` runs *before* the write (`proxy.py:374`), so the frame is never forwarded, the upstream thread dies, the server gets EOF. Exit code is 0 and nothing is recorded. |

Measured: with the surrogate reply as the first of three calls, 2 of 4 responses reached the client, then the proxy raised.

Suggested fix:
- Wrap both `capture.client_line(...)` and `capture.server_line(...)` calls in `try/except Exception`, forward regardless, and enqueue an alert on failure.
- In `_parse`, also catch `RecursionError`.
- In `digest()`, encode with `errors="surrogatepass"` (or `ensure_ascii=True`) so any JSON value can be digested.
- Add these three inputs to `tests/mcp/test_proxy.py` next to the malformed-frame test.

### D1 — A server can switch drift detection off (High)

Store writes fail open, and a failure only prints to stderr (`proxy.py`, `_write_events`). Nothing lands in the store, so the dashboard and `verify-chain` show a clean record.

- **Rug-pull plus one nameless entry.** After a pin exists, the server returns the changed tool list with one extra object that has no `name`. `diff_tools` does `str(tool["name"])` (`drift.py:45-46`) and raises `KeyError`. No integrity record is written. Reproduced: store holds only the original `artefact` and pin records.
- **Lone surrogate in a description on first contact.** `write_inventory` fails in `sha256_canonical`, so no inventory and no pin are ever written. Every later `tools/list` fails the same way. Reproduced: zero records.

Suggested fix:
- When `sink.apply` raises, write an `alert` record (code such as `proxy_capture_failed`, with the exception type and a digest of the frame). A capture failure is evidence.
- Make `diff_tools` total: a tool entry without a usable name is itself a drift (`modify`, "malformed tool entry"), not an exception.
- See B1 in section 3 for the surrogate case in canonical JSON.

### D2 — Duplicate tool names hide a changed tool (High)

`diff_tools` builds `{name: tool}` dictionaries, so the last entry wins. The proxy calls `write_inventory(..., minimum=None)`, which skips the uniqueness check in `enumerate_tools` (`inventory.py:110`).

```python
diff_tools([tool("scan")], [tool("scan", "MALICIOUS first copy"), tool("scan")])  # -> []
```

A client that takes the first match gets the malicious copy while the detector compares the benign one. Fix: treat a repeated name as drift and compare every copy; keep the uniqueness check on the proxy path.

### D3 — Changes outside name, description and inputSchema are invisible (High)

`describe_tool` (`inventory.py:80`) digests only those three fields. Changing `title` to an injection string, flipping `annotations.readOnlyHint`/`destructiveHint`, or adding an `outputSchema` returns no drift. Clients show `title` to the model and user, so it is as good a poisoning channel as `description`.

Fix: digest the whole tool object (after `hashable`), and report unknown-field changes as "schema changed". This changes `input_schema_digest` semantics or needs a new field, so it ties into the contract (P4).

### C1 — `cim inventory` then `cim sweep` says "no pin" (Medium)

```
$ cim inventory --db a.sqlite --tools-json corpora/mcp/tools_list.json   # ok, 150 tools
$ cim sweep     --db a.sqlite --tools-json corpora/mcp/tools_list.json
sweep: no pin for hexstrike; run inventory or the proxy first            # exit 2
```

Only the proxy writes the `mcp_pin` record (`proxy.py:243-256`); `cim inventory` does not, and `pinned_tools` (`drift.py:87`) looks for nothing else. The message tells the user to run the command they just ran. Fix: move pin writing into `write_inventory` (or a shared helper) so both paths pin. Also, `sweep` adds a new `mcp_server` artefact row each time it finds drift (`cli.py:169`).

### P2 — `cim proxy` hangs if the server command cannot start (Medium)

`run_proxy` starts the store-writer thread (`proxy.py:364`) before `subprocess.Popen` (`proxy.py:365`). If `Popen` raises (wrong path, not executable), the non-daemon writer blocks on `events.get()` forever and the process never exits. Reproduced: `cim proxy --db b.sqlite -- /nonexistent/server` had to be killed after 8 s. Fix: start the child first, or put `events.put(None)` in a `finally` that also covers `Popen`.

### D4 — The same drift is recorded on every re-read (Medium)

The pin never moves and there is no memory of what was already reported, so each `tools/list` after a change writes the full set of integrity records again. Three identical re-reads gave three identical records. A long session against a changed server floods the changes list. Fix: skip a drift whose detail already exists for that server since the pin, or record an acknowledged re-pin.

### D5 — Paginated `tools/list` looks like drift (Medium)

Each response is treated as the complete list. With `nextCursor`, page 1 becomes the pin and page 2 is diffed against it: "a: tool removed", "b: tool added". HexStrike answers in one page today, so this is latent. Fix: accumulate pages until a response has no `nextCursor`, then snapshot.

### P3 — Artefact rows and invocation ids across sessions (Medium)

- `StoreSink` only remembers artefact ids in memory. Every new proxy process creates a fresh `mcp_server` row and a fresh `mcp_tool` row per tool it sees. After four sessions: `('mcp_server','srv',4)`, `('mcp_tool','a',4)`. Records for one tool end up spread across several artefact ids.
- `invocation_id` is `f"{order:06d}:{message_id}"` (`proxy.py:269`) and `order` restarts at 1 per session. Three sessions gave `000001:2` three times. The contract treats it as an identifier.

Fix: look existing artefacts up before inserting (needs S5), and put a per-session id in `invocation_id`.

### P4 — Records that do not fit the T-02 contract (Medium)

- The pin is stored as kind `artefact` on an artefact of type `mcp_pin` with payload `{"code","server_id","name","tools"}`. `mcp_pin` is not one of the contract's artefact types, and the payload fails `McpArtefactPayload` validation (4 errors when wrapped in `Event`).
- Drift records put the human-readable sentence in `McpIntegrityPayload.path` and always leave `old_sha256`/`new_sha256` as `None` (`drift.py:110`), so an integrity record cannot be checked against a digest.
- Alert payloads are unvalidated (already in your v1.1 request).

The store accepts any dictionary, so nothing fails today, but T-13 and the correlation engine will read these through the contract. Proposal: add these to the v1.1 request in `docs/FASIH_REVIEW.md` — a pin payload type, a `detail` field on integrity payloads, and digests filled in on drift.

### E1 — Envelope (Low)

- `envelopes()` is a read path but `_connect` runs `CREATE TABLE IF NOT EXISTS` (`envelope.py:110`). Running `cim envelope` on a store that has no observations adds the `envelope_obs` table to it. An inspection command should not modify evidence.
- `record_observation` opens a new connection and runs the DDL for every call, and `with sqlite3.connect(...)` commits but does not close (`envelope.py:131`).
- `envelope_obs` sits outside the hash chain by design. T-16 will score on it, so anyone who can write the file can shape the baseline without breaking `verify-chain`. Worth one line in the threat model (A5).

### U1 — Skill records are shown as MCP records (Medium)

`load_board` sorts records by `kind` only (`board.py`, the `integrity` and `behaviour` branches). I wrote one skill integrity record and one skill behaviour record to a store and loaded the board:

- the integrity record appears under schema changes with an empty server and tool, and the file path as the detail;
- the behaviour record appears as a call to tool `unknown` with outcome `unknown`.

Nothing breaks today because no skill records exist yet. They will as soon as T-08 and T-10 write to a shared store. Fix: branch on whether the payload has `skill_id` or `server_id`, and either give skills their own lists or skip them until the board has a place for them.

### U2 — Dashboard load (Low)

The page polls `/api/board` every 2 s, and each request runs `verify_chain()` plus `read_records()` plus JSON parsing of every payload (`board.py:82-83`). Cost grows with the store and with the number of open tabs. It also opens the store through `BaselineStore`, which sets WAL and runs DDL, so the "read-only" page needs write access. Suggest caching by record count and opening with `mode=ro`.

### I1 — Float and string hash the same (Low)

`hashable` turns floats into strings (`inventory.py:25`), so `"default": 1.0` and `"default": "1"` give the same digest and no drift. Prefix the converted form (for example `"float:1"`).

### P5 — Batch frames (Low)

A JSON-RPC batch (an array) is valid in MCP 2025-03-26. `parse_frame` rejects it (`framing.py:35`), so it is alerted as malformed and any `tools/call` inside is not captured. The frame is still forwarded. Either unpack arrays or record the limit in ADR-004.

---

## 2. Baseline store T-06 — the review I owed (`common/store`, `common/chain.py`)

Checklist from `docs/FASIH_REVIEW.md`:

| Item | Result |
|------|--------|
| No update/delete API or DDL path | **Pass** |
| Tamper fails `verify_chain` with a clear `broken_at` | **Partly** — payload, kind and hash edits and mid-chain deletes fail correctly; see S2 and S3 |
| Genesis is 64 zeros; payloads use `canonical_json` | **Pass** |
| 10k appends under 5 s is honest | **Pass with a note** (S6) |
| Skills side can reuse the store for T-08 | **Not yet** — S1 and S5 |
| `cim verify-chain` exit codes 0 / 1 | **Pass** |

T-06 is already merged on org `main` (org PR #1, 2026-11-09), so these are fixes to `main`, not merge conditions. **S1 and S2 first:** T-08 and T-10 are built and are waiting on them before they can share a store with the proxy. The rest can follow.

### S1 — Two writers break the chain (High)

`BaselineStore` caches the tip hash in `_tip` (`baseline.py:71`, `147`, `209`) and never re-reads it, and the read-tip-then-insert step is not inside a write lock. Two handles on one file:

```python
A = BaselineStore(p)
B = BaselineStore(p)
A.append_record(a, "integrity", {"n": 1}, TS)
B.append_record(a, "integrity", {"n": 2}, TS)
A.append_record(a, "integrity", {"n": 3}, TS)  # chains from record 1, not 2
A.verify_chain()  # ok=False, broken_at=3, "prev_hash does not match the previous record"
```

This is ordinary use, not tampering: `cim sweep` while the proxy is running, two proxies sharing a store, and from T-08/T-10 the skills watcher and the MCP proxy writing to the same store. The result is a false "record was changed" on the dashboard that cannot be repaired (append-only).

Fix: do each append inside `BEGIN IMMEDIATE`, read the tip inside that transaction, and drop the cross-call cache (or use it only within an open `transaction()`). Set a `busy_timeout`. Add a two-handle test.

### S2 — Columns outside the hash can be edited freely (High)

`record_hash = SHA256(prev_hash || kind || payload)` (`chain.py:15`). `ts` and `artefact_id` are not covered, and neither is the `artefact` table.

```sql
UPDATE record   SET ts='1999-01-01T00:00:00Z', artefact_id=2 WHERE id=3;
UPDATE artefact SET name='evil', origin='elsewhere' WHERE id=1;
-- cim verify-chain: ok (5 records)
```

So a record can be re-dated or re-attributed to another tool or skill, and an artefact can be renamed, with the chain still "ok". SYS-14 says any historical edit breaks it.

The formula is the one in the plan (section 4.7), so this is a design change we both sign: hash `artefact_id` and `ts` as well, with a separator between fields, and cover the artefact row (hash it into its first record, or chain the artefact table too). This changes every stored hash, so it is cheapest to do now, before either of us keeps a store we care about.

### S3 — Deleting the newest records is not detected (Medium)

`DELETE FROM record WHERE id >= 4` leaves a valid shorter chain; `verify-chain` reports ok with 3 records. A full rewrite with recomputed hashes also passes, since there is no key. Both are inherent to an unanchored chain and belong to A5 / attestation (T-26), but it should be written down, and there is a cheap partial answer: print the tip hash and count in `verify-chain` and accept `--expect-tip` / `--min-count` so an operator or the verifier can pin them outside the file.

### S4–S6 — Smaller notes (Low)

- **S4** The timestamp check is a shape regex. `2026-13-45T99:99:99Z` is accepted (`baseline.py`, `_TS`; the same pattern is in `schema/envelope.py`).
- **S5** There is no way to find an existing artefact, which is why P3 happens. A `get_or_create_artefact(type, name, origin)` would fix it and is still append-only. The skills side works around it by reading the artefact id back from its own baseline record.
- **S6** The 10k test wraps all appends in one `transaction()`. With a commit per record, which is how the proxy writes, I measured about 7 s per 10k on my disk (btrfs). The acceptance line does not say which, so this is a note, not a failure. S1's fix will add some cost per append.

---

## 3. Border items — not changed, need both of us

These are in `common/schema/`, which I lead but which needs your review and a version bump. B1 to B3 are written and tested on a local branch, `t02-contract-fixes`, as contract revision 1.0.1. I will not push it until we have agreed them at the sync.

- **B1 `canonical_json` accepts strings it cannot hash.** A string with a lone surrogate passes `_check`, then `.encode()` fails later in `chain.py` or `sha256_canonical` with `UnicodeEncodeError`. This is the root of the second case in D1. Proposal: reject such strings (and keys) in `_check` with a clear `ValueError` naming the path.
- **B2 `Artefact` accepts stray ids.** `{"type": "skill", "skill": "a", "server": "x", "tool": "t"}` validates. Proposal: forbid ids that do not belong to the type.
- **B3 Timestamp.** Same as S4; validate with a real date parse in one shared place.
- **B4 Contract v1.1.** Your four rows in `docs/FASIH_REVIEW.md` plus P4 above (pin payload, `detail` on integrity, digests on drift) and D3 (what a tool digest covers). I suggest we settle these in one sitting.

---

## 4. What I changed on the skills side (for your review of my PRs)

| Branch | Task | State |
|--------|------|-------|
| `t05-cgroup-invocation` | T-05 cgroup scope per invocation, runner fixes | Org PR #2, CI green |
| `t05-seed-corpus` | T-05 seed corpus (11 benign, 3 suspicious) and checksum manifest | Committed locally |
| `t08-skills-inventory` | T-08 skill baselines and sweep | Committed locally |
| `t10-skills-watcher` | T-10 integrity watcher | Committed locally |

The branches are stacked in that order. T-08 and T-10 use the store API exactly as it is on `main`. They are correct with one writer; I am holding them back from sharing a store with the proxy until S1 is fixed, and any baseline written before S2 is settled is throwaway.

### Fixes in org PR #2

Each was reproduced first and has a regression test.

| Problem | Fix |
|---------|-----|
| A helper that exits within a few milliseconds and leaves a daemon behind was never detected or killed (missed 10 of 10 runs) | The helper is held behind a start gate until its cgroup is known. The leak check now always runs. |
| A helper could hide a process by creating a sub-cgroup inside its scope | Membership and the leak check are recursive. |
| Helper output that was not UTF-8, or a process name that was not UTF-8, crashed the runner | Output and `/proc` reads decode with replacement. |
| `run_script` failed (exit 127) when the skills root was a relative path | Script paths are made absolute. |
| `run_script` timeout killed only the main process; children kept running. Background children also made it wait for the full timeout. | The helper runs in its own process group, which is killed on timeout and after exit. Partial output is kept. |
| `run_script` passed the monitor's stdin to the helper | stdin is `/dev/null`. |
| A failed scope (for example a reused invocation id) looked like a helper that exited 1 | Raises `ScopeError`; the helper is not run. |
| The generated invocation id was not returned | `ScopedRunResult.invocation_id`. |
| Frontmatter: a BOM gave no metadata; `description: >-` gave the literal `>-` | BOM stripped; block scalars and continuation lines read. |
| One undecodable `SKILL.md` stopped discovery of every skill | Decoded with replacement. |

**Known limit, not fixed:** the scope runs as the same user as the helper, and systemd delegates that user's cgroup tree. A helper that writes a PID into a cgroup *outside* its scope moves that process out, and it is then neither attributed nor killed (reproduced). This needs a boundary a same-user process cannot cross (another uid, a cgroup namespace, or audit events) and belongs in T-11 and the threat model (A3). It is documented at the top of `src/cim/skills/scoped.py`.

---

## 5. Review of `t16-alerts-http-dashboard` (added 2026-11-15)

Branch at `e304196` (T-16 MCP alerts, T-16b HTTP gateway, dashboard buttons). Its own tests pass. G1 to G4, X1, X2 and A1 were reproduced on a copy of the branch with local stand-in servers; nothing was sent to a real MCP service. A2 and G5 to G7 are from reading the code.

| # | Area | Problem | Severity |
|---|------|---------|----------|
| G1 | Gateway | Any local caller, and any web page in the operator's browser, gets the stored bearer token attached | High |
| G2 | Gateway | The path after `/s/<id>/` can leave the configured endpoint: `..`, and other URL schemes | High |
| G3 | Gateway | A redirect from the upstream carries the bearer token to another host | High |
| X1 | Dashboard | `POST /api/call` can wipe or rewrite the store, with no check on who asks | High |
| X2 | Dashboard | The "change" button writes its own behaviour alert; the detector did not produce it | High (for the demo) |
| A1 | Alert | One alert, then silence: the unusual call joins the baseline | Medium |
| A2 | Alert | T-16 is specified as a shared scorer; this one is MCP-only and has no z-score or threshold | Medium |
| G4 | Gateway | Same fail-open breaks as P1: some bodies get no response at all | Medium |
| G5 | Gateway | Responses are read to the end before anything is sent on, so streams stall | Medium |
| G6 | Gateway | One capture per route: request ids from two sessions collide | Low |
| G7 | Config | A real Supabase project reference is committed | Low |

### G1 — The gateway lends its stored credentials to anyone who can reach it (High)

`authorization_env` adds `Authorization: Bearer <token>` whenever the client sent none (`http_gateway.py:191`, `_authorization_for`). The gateway has no check on who the client is: no secret of its own, no `Origin` check, no `Host` check.

Reproduced: a request with no credentials, `Origin: http://evil.example` and `Host: evil.example` was forwarded with `Authorization: Bearer s3cret-token`, and it was a `tools/call`.

Who can do that:
- any process on the machine;
- a web page open in the operator's browser. A cross-site `fetch` to `http://127.0.0.1:8877/s/supabase` is sent by the browser, the gateway adds the token and forwards it. With DNS rebinding the page can also read the answers, because nothing validates `Host`.

So a page the operator merely visits can send requests to the Supabase, Vercel, Axiom and Roma MCPs with the operator's tokens attached. The MCP specification asks local HTTP servers to validate `Origin` for exactly this reason.

Suggested fix: require a per-run secret from the client (a random path segment or header, written into Cursor's `mcp.json`), reject requests whose `Host` is not the gateway's own address, and reject any `Origin` that is not expected. Inject the stored token only after those pass.

### G2 — The request path can leave the configured endpoint (High)

`join_upstream` hands the client's path to `urljoin` (`http_gateway.py:168-177`).

- `GET /s/up/../../admin/keys` reached the upstream as `/admin/keys`, with the bearer token attached. The route was configured for `/mcp` only.
- `GET /s/up/file:/etc/hostname` makes `urljoin` return `file:/etc/hostname`, and `urlopen` opens the local file. The content does not come back today only because the handler then crashes on a missing status code (`TypeError` in `send_response`). That is an accident, not a control.

Suggested fix: after joining, require the result to have the upstream's scheme and host and to start with the upstream's path; refuse anything else with 400.

### G3 — A redirect leaks the token (High)

`urlopen` follows redirects and keeps the `Authorization` header. Reproduced: the upstream answered `302` to a second host, and that host received `Authorization: Bearer s3cret-token`. A compromised or malicious upstream can therefore collect the token for itself or for another service. Suggested fix: build an opener that does not follow redirects and pass the 3xx back to the client.

### X1 — The dashboard can wipe and rewrite the store (High)

`serve.py` now has `POST /api/call` with `clear` and `tamper` actions (`call_demo.py:49` and `219`). `clear` runs `DELETE FROM` on every table; `tamper` rewrites the first record.

Reproduced on a store with five records, sending `Origin: http://evil.example` and `Content-Type: text/plain` (a request a browser sends cross-site without asking first):

```
tamper -> 200, chain_ok false
clear  -> 200, records 0, artefacts 0
cim verify-chain -> ok (0 records)
```

Three problems in one:
- This is in `cim dashboard`, which runs against whatever `--db` it is given, including a real evidence store. It is not limited to a demo store.
- Any web page the operator visits can trigger it. After `clear`, `verify-chain` reports a healthy, empty chain (S3).
- T-06's acceptance says no update or delete code path exists. One now does, in the package.

Suggested fix: move the demo actions out of the product server into a separate command that only accepts a store it created itself (for example a marker table), and keep `cim dashboard` read-only. If the buttons must stay, require a per-run token and check `Origin`.

### X2 — The demo alert is written by the button, not by the detector (High for the demo)

`run_demo_call(unusual=True)` calls `_warn_behavior` (`call_demo.py:176`), which appends a fixed `mcp_behaviour_drift` alert: detail "Strange behaviour detected.", features `["hidden copy"]`, with prepared input and output sentences.

Reproduced: one press of "change" on an empty store gives that alert with a single observation recorded. The real scorer cannot fire before 30 calls. The alert is stored in the hash chain like real evidence, and the page then shows the server as disconnected, although nothing was disconnected (the flag lives in a `.session` file).

`PROJECT_STATUS.md` on the branch says the T-16 MCP half is "live done". If the board is shown to the committee, the alert on screen has to come from `score_latest`, or it has to be labelled as staged. I would do the former: have the button make 31 ordinary calls first and let the scorer speak.

### A1 — One alert, then silence (Medium)

Every observation joins the baseline, including the one that just raised an alert. Reproduced with `StoreSink`: 31 normal calls, then five identical calls with a new `bcc` argument holding a public address. Alerts after each of the five: 1, 1, 1, 1, 1. The second and later malicious calls are already "normal".

The same mechanism means a tool that misbehaves from its first call never alerts (59 such calls: no alert). That part is inherent to learning a baseline from live traffic, and the plan answers it with thresholds calibrated on the benign corpus. The first part is a choice: keep an observation out of the baseline while its alert is unacknowledged.

### A2 — Not yet the shared scorer the plan describes (Medium)

T-16 is "shared library used by both sides, lives at the border": rolling z-score plus never-seen flag, composite score, configurable threshold. `cim/mcp/alert.py` reads MCP's `envelope_obs` table directly, has fixed rules (new class, new shape, first error, result three times the median), no threshold to configure, and nothing the skills side can call. It also reads every observation the tool has ever had on each call.

Proposal: a small scorer in `common/` that takes two things and knows nothing about where they came from: support sets (value, count) and integer summaries (count, sum, sum of squares). `cim.skills.envelope.SkillProfile` on `t15-skills-envelope` already has exactly that shape, and the MCP envelope can produce it from `envelope_obs`. I can draft it for us both to review.

### G4 — Some bodies get no response (Medium)

Same class as P1. A response containing a lone surrogate, and a deeply nested request body, both end with the client's connection closed and no reply (`UnicodeEncodeError` in `_json_line`, `RecursionError` in `json.loads`). In the second case the request is never forwarded. Capture runs before the reply is written (`_write_upstream`), so a capture failure costs the client its answer. Suggested fix: write the reply first, capture after, and wrap capture in `try/except Exception`.

### G5 — Streams stall (Medium)

`_write_upstream` calls `resp.read()` before sending anything. A long-lived `text/event-stream` (the Streamable HTTP GET stream, or a slow tool that streams progress) is held until the upstream closes or the 120 s timeout. Short JSON and single-event replies work, which is what the unit tests cover.

### G6, G7 — Smaller notes (Low)

- **G6** There is one `Capture` per route, keyed by JSON-RPC id. Two Cursor sessions on the same route both start their ids at 1, so a response can be paired with the other session's request and the wrong tool recorded.
- **G7** `config/cursor-http-gateway.json` commits a real Supabase `project_ref` and the list of services on your machine to the committee repo. Suggest committing an example file with placeholders and keeping the real one out of git. Request paths, including query strings, are also written to stderr by `log_message`.
