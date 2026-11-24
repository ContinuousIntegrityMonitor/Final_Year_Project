# MCP test report, for Hamza

Asked for in [`docs/FASIH_ASK_2026-11-19.md`](FASIH_ASK_2026-11-19.md), part B and C. Issue #19.

| | |
|---|---|
| Date | 2026-11-23 |
| Tested by | Fasih's assistant, for Fasih |
| Machine | Fedora Linux 44 (Workstation), kernel 7.3.3, x86_64 |
| Tools | uv 0.13.0, project Python 3.12.15 (from `uv sync`), `mcp` SDK 1.30.0; no Node.js |
| Commit | org `main` @ `a81681704b0b7e2658f323550b7ddc5c16accf8a` (merge of PR #18) |

**In short:** every suite is green, and the T-16 and T-16b paths both raise the expected `mcp_behaviour_drift` alert for `private_ip` after warm-up. All refusal checks give 401. Testing from other angles found one High security fault in the gateway: it attaches the stored Bearer token with no gateway token set, and that is the default. It also found that the live scripts are not in git, plus five Medium faults. Each claim below was run, except where it says *from reading*.

## 1. Pass / fail

| # | Command | Result | Output |
|---|---|---|---|
| 1 | `git checkout -b … org/main` | pass | `a816817` |
| 2 | `uv sync --all-extras` | pass | `Checked 60 packages`, exit 0 |
| 3 | `uv run pytest -m "not sys and not lab"` | pass | `286 passed, 2 deselected in 27.78s` |
| 3b | `uv run pytest -m "not lab"` (adds the sys tests) | pass | `288 passed in 27.33s` |
| 4 | `uv run pytest tests/mcp` | pass | `66 passed in 4.29s` |
| 4b | `ruff format --check .`, `ruff check .`, `mypy src/cim` | pass | `133 files already formatted`, `All checks passed!`, `Success: no issues found in 46 source files` |
| 5a | `scripts/_live_t16_warmup.py` | **not runnable** | File is not in git (finding H2). Replaced by 5a′ |
| 5a′ | `scripts/live_t16_stdio.py` (new, this PR) | pass | 37 `behaviour` records; 1 alert `shout changed how it is used: value class private_ip`; `RESULT: PASS` |
| 5b | `scripts/_live_t16b_http_warmup.py` | **not runnable** | File is not in git (H2). Replaced by 5b′ |
| 5b′ | `scripts/live_t16b_http.py` (new, this PR) | pass | 36 `behaviour` records; 1 alert `echo changed how it is used: value class private_ip`; Bearer not in store files or gateway log; `RESULT: PASS` |
| 6a | `cim verify-chain` on the 5a′ store | pass | `ok (42 records)` |
| 6a | `cim verify-chain` on the 5b′ store | pass | `ok (40 records)` |
| 6b | `cim dashboard --db <store> --once`, both stores | pass | exit 0, 35 KB / 34 KB page, alert shown |
| 6c | `cim dashboard --demo`, `POST /api/call` | pass | no token 401, wrong token 401, right token + bad Origin 401, right token + bad Host 401, right token 200; read-only server 404 |
| 6d | Gateway refusals (`CIM_HTTP_GATEWAY_TOKEN` set) | pass | missing token 401, wrong token 401, bad Origin 401, bad Host 401; upstream reached by refused requests: 0 |
| 7 | `python -m cim.skills corpus verify`, `inventory`, `sweep` on the seed corpus | pass | `manifest verifies`; `skills=14 new_baselines=14 chain=ok`; `unchanged`; `verify-chain: ok (14 records)` |

**How 5a′ differs from Playwright.** Playwright MCP needs Node (`npx`), which this machine does not have. 5a′ runs the official MCP SDK client against the SDK server in `tests/mcp/sdk_server.py`, through a real `cim proxy` process. That is the same proxy → store → envelope → scorer path, with a real SDK session at both ends. It warms up `shout` for 35 calls, makes one `add` call, then calls `shout("10.0.0.5")`. The Playwright run itself still needs a machine with Node, or VM-MON.

**How 5b′ works.** It starts a fake Streamable-HTTP upstream and a real `cim http-gateway` process with a route that uses `authorization_env`. It makes 35 warm-up `echo` calls, then `echo("http://192.168.1.10/admin")`, then the refusal checks. After that, a second gateway runs **without** a gateway token for the probes in section 2. The probes print what happened; they are not pass/fail gates.

## 2. What broke

Nothing in the suites or the requested checks failed. The findings come from the extra angles.

| Probe (5b′ / dashboard) | Seen |
|---|---|
| a. No gateway token; `Origin: null`; `Content-Type: text/plain` body | 200, and the upstream received `Authorization: Bearer <stored token>` |
| b. Path `/s/fake/%2e%2e/admin` | 200; upstream received path `/mcp/%2e%2e/admin` with the Bearer attached |
| c. Upstream SSE stream: one event at 0 s, closes at 6 s | Client got its first byte at **6.0 s** |
| d. Two clients, both use JSON-RPC id 7, calls overlap | 2 calls made, **1** `behaviour` record |
| e. Dashboard `GET /` with `Host: evil.example` (demo mode) | 200, and the page contains the demo token |
| f. Store copy: one `UPDATE envelope_obs` marking earlier `shout` rows as `public_ip` | Clean copy alerts `value class public_ip` on a call to `8.8.8.8`; edited copy gives no alert; `verify-chain` ok on both |

## 3. Improvement suggestions

Fasih did not change anything under `src/cim/mcp/` or `src/cim/dashboard/`. Each item says where the fix would go.

### High

**H1. With no gateway token, the gateway still lends the stored Bearer token to any caller.** `http_gateway.py` attaches `authorization_env` whenever it is set (`_authorization_for`, in `_proxy`). `access_token` is only checked if it is non-empty. The comment on `GatewayConfig.access_token` says the token is "Required before any stored Bearer token is attached". The code does not enforce that. `config/cursor-http-gateway.json` sets no token, and `docs/setup/cursor-http-mcp-gateway.md` never mentions `CIM_HTTP_GATEWAY_TOKEN`, so the documented setup runs the open way. The consequences:
- Any local process can call Vercel / Supabase / Axiom / Roma tools as the user.
- `Origin: null` is accepted, and a plain-text JSON body is parsed. A sandboxed iframe or a `file://` page sends exactly that, with no CORS preflight. So a web page can also fire tool calls, in browsers that do not block public-to-loopback requests. It cannot read the reply, but the call (for example a deploy or an SQL statement) still runs. Probe a.

Suggested fix:
- Refuse to start, or refuse to attach the Bearer, when any route has `authorization_env` and no gateway token is set.
- Drop `"null"` from the allowed Origins (also in `dashboard/serve.py`).
- Require `Content-Type: application/json` on POST.
- Document the `headers: {"X-CIM-Gateway-Token": …}` entry Cursor needs in `mcp.json`.

**H2. The live acceptance scripts are not in git.** `.gitignore:52` ignores `scripts/_*`. That covers `_live_t16_warmup.py`, `_live_t16b_http_warmup.py` and `_ship.sh`, and no branch on either remote has them. The T-16 / T-16b progress files cite them as evidence, but nobody else can rerun them. Suggested fix: commit them under names without the underscore, or narrow the ignore rule. This PR adds `scripts/live_t16_stdio.py` and `scripts/live_t16b_http.py` as stand-ins. Keep them, replace them with yours, or drop them, as you prefer.

### Medium

**M1. The scorer's input is outside the hash chain.** `score_latest` reads `envelope_obs`, which `envelope.py` calls "derived data, not hash-chained evidence". One `UPDATE` there decides whether an alert fires, and `verify-chain` still passes (probe f). An attacker who can write to the store, which is exactly what the chain defends against, can teach the scorer that an IP class is normal. Suggested fix: put argument shape, value classes and result size into the chained `behaviour` payload, and derive the envelope from the chain. That is a schema change, so it fits in the v1.1 contract revision Fasih is preparing (ask A4). The other option is to chain the observations.

**M2. The gateway holds the whole upstream reply before sending any of it.** `_write_upstream` calls `resp.read()`, so SSE events reach Cursor only when the stream ends (probe c: 6 s late). That holds up progress events on long tool calls, and a GET stream that stays open never reaches the client. *From reading:* after the 120 s timeout the read raises `TimeoutError`, which the `URLError` handler does not catch, so the client loses the connection with no response. Suggested fix: pass SSE through chunk by chunk and capture each event as it goes by.

**M3. Two sessions on one route can lose each other's calls.** There is one `Capture` per route, and pending calls are keyed by JSON-RPC id alone. Two Cursor windows, or a reconnect, both counting from 1, overwrite each other's pending entry (probe d: 2 calls, 1 record). Suggested fix: key on `Mcp-Session-Id` plus the id, or keep one `Capture` per session.

**M4. Two places where a fault is not recorded.**
- `_StoreWriter._run` in the gateway logs a failed write but does not call `sink.record_failure`. The stdio proxy has done that since PR #12, so a gap in the record is itself recorded.
- In `StoreSink.apply`, a scorer exception is swallowed with `pass`, although the comment says "a scorer fault is logged by the writer".

Both mean an alert can be missed without trace. Suggested fix: record `proxy_capture_failed` with `stage: "store"` / `stage: "score"` in both places. *From reading.*

**M5. The dashboard checks Host only on POST.** `do_GET` has no Host check, so a DNS-rebinding page can read `/` and `/api/board`: tool names, alert details, call counts. In `--demo` mode the page also carries the demo token (probe e). Writes stay safe, because POST checks Host and the server answers the preflight with 501. Suggested fix: run `_client_allowed`'s Host check on every route.

### Low

- **L1.** `join_upstream` checks for `..` before decoding, so `%2e%2e` gets through with the Bearer attached (probe b). Whether the upstream treats it as `..` depends on that server. Decode, or reject `%2e`, before the check.
- **L2.** Token comparisons use `!=` (gateway and dashboard). `hmac.compare_digest` is the usual choice.
- **L3.** The `make_server` docstring says the demo token can also come in the query or body. Only the header works: `?token=` gives 401.
- **L4.** `docs/setup/cursor-playwright-cim.md` is Windows-only (`npx.cmd`, `%USERPROFILE%`). A Linux line would help, since VM-MON is Linux.
- **L5.** The repo is public. `config/cursor-http-gateway.json` carries a Supabase `project_ref` and a personal route list. They are not secrets, but they identify the project. Consider a tracked `*.example.json` plus an untracked local config.
- **L6.** No tests cover the H1, M3 or M2 cases, or `Origin: null`. Add them with the fixes.
- **L7.** Warm-up learns whatever happens in the first 30 calls. A `private_ip` call during warm-up is never flagged later. This is by design, but worth stating in the threat model (T-03).

## 4. For Hamza to decide

1. **H1:** refuse to start without a token, or start but never attach the Bearer without one? Fasih's preference is to refuse to start when any route has `authorization_env`.
2. **M1:** move the envelope features into the chained `behaviour` payload (part of contract v1.1), or chain `envelope_obs` as it is?
3. **H2:** keep the two stand-in scripts in `scripts/`, or replace them with yours?
4. Who fixes H1 and M2 to M5? They are in `src/cim/mcp/` and `src/cim/dashboard/`, so Fasih has not touched them. Fasih's assistant can prepare a PR if you agree first.
