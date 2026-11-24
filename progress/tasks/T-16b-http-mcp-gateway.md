# T-16b - HTTP MCP gateway (Cursor URL servers)

- Owner: H | Status: Done | Window: brought forward 2026-11-12 | Completed: 2026-11-19 (PR #16); H1+U1 in #28
- Depends on: T-09 (stdio proxy), T-16 MCP scorer path
- Decision: ADR-005
- Ship: [PR #16](https://github.com/ContinuousIntegrityMonitor/Final_Year_Project/pull/16) on `t16-alerts-on-main` (2026-11-19)

## Goal

Watch MCP servers Cursor reaches by **URL** (Streamable HTTP), the same way
`cim proxy` watches **stdio** servers. Target Cursor entries: Roma, Vercel,
Supabase, Axiom, and local HTTP MCPs (Graphiti).

## Done in code

- [x] `cim http-gateway` + `config/cursor-http-gateway.json`
- [x] Capture reuses stdio `Capture` / `StoreSink` (list + call → store / envelope / T-16)
- [x] Auth headers forwarded; not written into the chain; optional `authorization_env`
- [x] Unit test with fake upstream (JSON + SSE)
- [x] Cursor `mcp.json` URL entries pointed at `http://127.0.0.1:8877/s/<id>`
- [x] How-to: `docs/setup/cursor-http-mcp-gateway.md`
- [x] G1: Host/Origin check + optional `CIM_HTTP_GATEWAY_TOKEN` before attaching Bearer
- [x] G2: `join_upstream` refuses path escape / scheme change
- [x] G3: opener does not follow redirects

## Acceptance tests (operator / live)

- [x] Live script warm-up + unusual → `mcp_behaviour_drift` (`scripts/_live_t16b_http_warmup.py`, 2026-11-19)
- [ ] Gateway running; a Cursor URL MCP (start with Graphiti if local) records `tools/list` and `tools/call` in `logs/cursor-http.sqlite`
- [ ] Pin + rug-pull path works for an advertisement change on that server
- [x] After warm-up, T-16 behaviour alert fires on unusual live traffic (fake upstream path)
- [ ] `cim dashboard --db logs/cursor-http.sqlite` shows a real Cursor session; `cim verify-chain` passes
- [ ] Stdio HexStrike / Playwright path remains unchanged and green on VM-MON
- [ ] OAuth URL servers: set `CIM_MCP_AUTH_*` when Cursor cannot re-auth against localhost

## Notes

- Out of scope for T-09. Do not pretend URL servers are covered by stdio wrap.
- Not a substitute for VM-MON HexStrike.
- Dashboard product path is read-only unless `cim dashboard --demo`.
