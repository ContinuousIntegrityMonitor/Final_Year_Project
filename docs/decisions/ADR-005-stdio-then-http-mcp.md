# ADR-005: Stdio proxy and HTTP MCP gateway (both transports)

- **Date:** 2026-11-12
- **Status:** Accepted (path 2 brought forward the same day)
- **Decided by:** Hamza Farooq

## Context

Cursor connects some MCPs as local **stdio** processes (`command` + `args`) and others
as **URL** / Streamable HTTP servers (`url`). CIM’s T-09 proxy only sits on stdio
(plan §4.8). Full Cursor coverage therefore needs two transports. December C1–C5
still depends on stdio (HexStrike on VM-MON).

## Options considered

1. **Stdio only:** matches the FYP plan and HexStrike; cannot watch Roma, Vercel,
   Supabase, Axiom, or other URL MCPs in Cursor.
2. **HTTP only:** would watch URL MCPs; would miss HexStrike and break the graded
   stdio demo path.
3. **Both, sequenced:** stdio live path first; HTTP gateway next (chosen). Originally
   scheduled for December; Hamza asked to implement path 2 immediately after path 1.

## Decision

- **Path 1 (stdio):** keep and use the stdio `cim proxy`. Cursor Playwright is wrapped
  through it for live T-16 on this PC (`docs/setup/cursor-playwright-cim.md`).
  HexStrike on VM-MON remains the lab demo.
- **Path 2 (HTTP):** `cim http-gateway` sits in front of Cursor URL MCPs, writes into
  `logs/cursor-http.sqlite`, and uses the same envelope / T-16 scorer / dashboard.
  Config: `config/cursor-http-gateway.json`. How-to:
  `docs/setup/cursor-http-mcp-gateway.md`. Tracked as
  `progress/tasks/T-16b-http-mcp-gateway.md`.
- Path 2 does **not** replace path 1. Both are required for “every MCP in Cursor”
  plus the FYP HexStrike demo.
- OAuth: gateway forwards `Authorization` and never logs it. Cursor OAuth against the
  real host does not apply to localhost URLs; optional `authorization_env` injects a
  Bearer from the environment when needed.

## Consequences

- Operator docs name which Cursor servers use which transport and which store file.
- Quarantine (T-29) will need hooks on both transports.
- Live warm-up for URL servers still needs the gateway process running before Cursor connects.
