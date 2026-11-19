# 2026-11-12 — Cursor stdio wrap + HTTP MCP gateway

- Cursor Playwright MCP is launched through `cim proxy` into
  `logs/cursor-playwright.sqlite` (path 1 / stdio). How-to:
  `docs/setup/cursor-playwright-cim.md`.
- Path 2 brought forward the same day: `cim http-gateway` +
  `config/cursor-http-gateway.json` records URL MCPs into
  `logs/cursor-http.sqlite`. How-to: `docs/setup/cursor-http-mcp-gateway.md`.
  Cursor `mcp.json` URL entries point at `http://127.0.0.1:8877/s/<id>`.
- OAuth URL servers need `CIM_MCP_AUTH_*` env tokens when Cursor cannot re-auth
  against localhost; secrets are not written into the hash chain.
- HexStrike on VM-MON remains the graded lab session after live alerts work on
  this PC.
