# Event contract 1.1.0

T-02, Fasih (lead). Answers Hamza's v1.1 request in [`docs/FASIH_REVIEW.md`](FASIH_REVIEW.md). Four rows, **all four answers agreed by Fasih on 2026-11-24**. The other v1.1 needs are in the same revision: the scorer design (PR #22), the T-13 design (PR #25), and review P4 / D3. **Hamza reviews it in this PR** (border change).

- **Code:** `src/cim/common/schema/` (`mcp.py`, the new `alerts.py`, `envelope.py`, `__init__.py`, `canonical.py`).
- **Tests:** `tests/common/test_schema_v11.py`, `tests/common/test_canonical.py`, `tests/common/test_schema_envelope.py`.

## 1. Compatibility

- **Additions only.** Every field added to an existing payload is optional, and every 1.0 payload still validates (`test_v10_payloads_still_validate`). So `SCHEMA_VERSION` stays 1, and `CONTRACT_VERSION` becomes `1.1.0`.
- **No writer has to change for this PR to merge.** The full suite passes unchanged.
- **One visible effect:** writers that dump these models now write the new keys with `null` values (and `"record": "baseline"` on MCP baselines) until they fill them in. Every reader uses `.get`, so nothing breaks.
- **Hash formula unchanged:** that is ADR-006 (S2), a store change, decided separately.

## 2. What changed

### 1.0.1: validation fixes (from `t02-contract-fixes`, 2026-11-15)

| | Rule |
|---|---|
| B1 | `canonical_json` rejects a string or key that is not valid Unicode text (a lone surrogate), naming the path, instead of failing later inside the store |
| B2 | An artefact may only carry the identifiers of its own type (a skill artefact cannot also set `server`) |
| B3 | `Event.ts` must be a real date and time: `2026-13-45T99:99:99Z` was accepted |

### 1.1.0: Hamza's four rows, as answered

| # | Asked | Agreed | Where |
|---|---|---|---|
| 1 | `response_size` on MCP calls | `response_bytes: int ≥ 0`, optional | `McpBehaviourPayload` |
| 2 | `method: "tools/call"`, with the order kept in `invocation_id` | `session_id` and `seq` (≥ 1). They come together, and when set `invocation_id` must equal `<session_id>:<seq>`. That makes ids unique across sessions (review P3) | `McpBehaviourPayload` |
| 3 | `McpSessionPayload` under `mcp_server` + `artefact` | Accepted, with a `record` field on every MCP artefact payload: `"baseline"` (the default; a 1.0 payload without `record` is a baseline), `"session"` or `"pin"`. Session and pin records belong to an `mcp_server` artefact only | `McpArtefactPayload`, `McpSessionPayload`, `McpPinPayload` |
| 4 | `ProxyAlertPayload` | Accepted. Every alert has `code` and `reason`. The three proxy alert shapes written today already conform (`test_proxy_alerts_as_written_today_already_conform`) | `alerts.py` |

### 1.1.0: bundled from the other designs

| Field or payload | Why | Where |
|---|---|---|
| `argument_shape_digest`, `value_classes` (sorted, from the five envelope classes) on MCP calls | Scorer inputs move into the chain (test report M1, scorer design 6) | `McpBehaviourPayload` |
| `BehaviourAlertPayload` (`mcp_behaviour_drift`, `skill_behaviour_drift`): side ids, `observation_record_id`, `composite_milli`, 1 to 3 `DriftFeature`s in integer milli-z, `window`, `scorer_version`, `detail` | Shared alert shape (scorer design 7) | `alerts.py` |
| Artefact type `monitor` (id field `component`); `MonitorAlertPayload` (`collector_restarted`, `collector_failed`) | Watchdog restarts in the chain (T-13 design 6) | `envelope.py`, `alerts.py` |
| `McpPinPayload` (`record: "pin"`) | The pin had no contract shape (review P4) | `mcp.py` |
| `detail` on MCP integrity payloads | Drift text no longer has to go in `path` (review P4) | `McpIntegrityPayload` |
| `tool_digest` on tool descriptors: digest of the whole canonical tool object | `input_schema_digest` misses `title`, `annotations`, `outputSchema` (review D3). The detector compares whole objects since PR #13; now the stored digest can too | `McpToolDescriptor` |

### How alerts are checked

- An alert payload must have a string `code`.
- Codes in `ALERT_PAYLOADS` are validated by their model, and must sit under an artefact type that fits the code (a skill alert under a `skill` artefact, and so on). Their ids must match the artefact's.
- Codes not listed yet pass with only the `code` check, so either side can add a code before the contract lists it.

## 3. What each side does to adopt it (later PRs)

| Side | Change | When |
|---|---|---|
| MCP (Hamza) | Proxy and gateway: fill `response_bytes` (the response size already measured), `session_id` (one per proxy run) + `seq`, `argument_shape_digest`, `value_classes`; write a `session` record from `initialize` | your next proxy PR |
| MCP | `write_pin`: write the pin under the server's `mcp_server` artefact with `record: "pin"`, instead of an artefact of type `mcp_pin`, which the contract does not know | same |
| MCP | Drift: put the words in `detail` and keep `path` a path; fill the digests | same |
| MCP | Inventory: fill `tool_digest`. Existing pins and baselines keep validating without it | same |
| MCP | Validate through `Event` before writing, as the skills side does in `append_event`, so nothing the contract refuses reaches the store | same |
| Both | `mcp_behaviour_drift` / `skill_behaviour_drift` move to `BehaviourAlertPayload`. Today's MCP drift alert shape (features as plain strings) does not conform (`test_behaviour_alert_as_written_today_does_not_conform_yet`). Nothing validates alerts at write time today, so nothing breaks meanwhile | the scorer PR (T-16) |
| Both | `collector_restarted` / `collector_failed` under `monitor` artefacts | the watchdog PR (T-13) |

## 4. Decisions recorded

- **Hamza's four rows:** agreed as answered (Fasih, 2026-11-24). Hamza reviews them here.
- **D3:** a tool's stored digest should cover the whole tool object. `tool_digest` is added next to `input_schema_digest`, not instead of it, so no existing digest changes meaning.
