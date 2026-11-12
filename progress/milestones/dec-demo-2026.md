# December 2026 demo — C1–C6

- Status: in progress (Phase 1 / FYP I gate; target ~1 Dec 2026)
- Scope: ADR-003 — functional SEE path; product polish deferred to FYP II
- Local suite passed on 2026-11-09 (`uv run pytest -q`). That run does not include a HexStrike tool call.

## Criteria

- C1 inventory: automated pass, and the pinned HexStrike `tools/list` (150 tools) is saved in `corpora/mcp/tools_list.json`. The VM-MON capture is still open.
- C2 benign session capture: automated pass (100-call replay and an MCP SDK session through `cim proxy`). Live HexStrike session not done.
- C3 rug-pull alert: automated pass (`send_email` description rewritten and a `bcc` parameter added). Live sweep not done.
- C4 trigger behavioural alert: in progress. Envelope + MCP scorer exist. Live stdio path: Cursor Playwright through `cim proxy`. Live URL path: `cim http-gateway` (`docs/setup/cursor-http-mcp-gateway.md`). HexStrike on VM-MON still required for the graded lab story.
- C5 status + chain verify: partial. `cim verify-chain` passes in tests. `cim dashboard` home page shows counts and whether something new appeared; the list is behind "See the list". `cim status` is still the T-13 stub.
- C6 backup video: not achieved.

## Cursor coverage (ADR-005)

- **Stdio:** Playwright in Cursor is wrapped by CIM. Same transport as HexStrike.
- **HTTP:** T-16b `cim http-gateway` wraps Cursor URL MCPs (Roma, Vercel, Supabase, Axiom, Graphiti). Extra committee-facing Cursor coverage; **not** a substitute for HexStrike C2/C4. Live warm-up still open.

## Building blocks

- T-01 infra/CI Done
- T-02 contract Done (PR #8)
- T-04 MCP lab Done (PR #162) — pin and topology. The pinned checkout is on the dev PC at `D:\lab\hexstrike-ai`; VM-MON is not booted.
- T-05 skills runner skeleton Done (PR #6)
- T-06–T-14 + status board on the org shipped line
- T-16 MCP half in progress (live stdio via Cursor Playwright)
- T-16b HTTP MCP gateway code on this PC (2026-11-12); live URL warm-up open

## Remotes

Push accepted phases to both `origin` and `org` (ADR-002). Do not push the pre-rebuild history.
