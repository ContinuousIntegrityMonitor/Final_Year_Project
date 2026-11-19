# T-16b - HTTP MCP gateway (Cursor URL servers)

- Owner: H | Status: in progress | Window: brought forward 2026-11-12 | Completed:
- Depends on: T-09 (stdio proxy), T-16 MCP scorer path
- Decision: ADR-005

## Goal

Watch MCP servers Cursor reaches by **URL** (Streamable HTTP), the same way
`cim proxy` watches **stdio** servers. Target Cursor entries: Roma, Vercel,
Supabase, Axiom, and local HTTP MCPs (Graphiti).

## Done in code (2026-11-12)

- [x] `cim http-gateway` + `config/cursor-http-gateway.json`
- [x] Capture reuses stdio `Capture` / `StoreSink` (list + call → store / envelope / T-16)
- [x] Auth headers forwarded; not written into the chain; optional `authorization_env`
- [x] Unit test with fake upstream (JSON + SSE)
- [x] Cursor `mcp.json` URL entries pointed at `http://127.0.0.1:8877/s/<id>`
- [x] How-to: `docs/setup/cursor-http-mcp-gateway.md`

## Acceptance tests (operator / live)

- [ ] Gateway running; a Cursor URL MCP (start with Graphiti if local) records `tools/list` and `tools/call` in `logs/cursor-http.sqlite`
- [ ] Pin + rug-pull path works for an advertisement change on that server
- [ ] After warm-up, T-16 behaviour alert fires on unusual live traffic
- [ ] `cim dashboard --db logs/cursor-http.sqlite` shows the session; `cim verify-chain` passes
- [ ] Stdio HexStrike / Playwright path remains unchanged and green
- [ ] OAuth URL servers: set `CIM_MCP_AUTH_*` when Cursor cannot re-auth against localhost

## Notes

- Out of scope for T-09. Do not pretend URL servers are covered by stdio wrap.
- Not a substitute for VM-MON HexStrike.
