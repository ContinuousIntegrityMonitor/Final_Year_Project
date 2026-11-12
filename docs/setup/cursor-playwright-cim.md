# Cursor Playwright through CIM proxy (live T-16)

Path **1** (stdio). Cursor launches `cim proxy`; the proxy launches Playwright MCP. Calls land in `logs/cursor-playwright.sqlite`. URL MCPs (Roma, Vercel, …) stay direct until the December HTTP gateway (path **2**, ADR-005).

## One-time config

Already applied in `%USERPROFILE%\.cursor\mcp.json` for the `playwright` server:

- `uv run … cim proxy --db logs/cursor-playwright.sqlite -- npx.cmd -y @playwright/mcp@latest`
- Env: `CIM_PROXY_SERVER_ID=playwright`, `CIM_PROXY_ORIGIN=cursor`, `CIM_PROXY_ROOT=cursor-playwright`

Project root on this PC:

`d:\Final Year Project\New folder\New folder\New folder\New folder\Final Year Project`

## Each session

1. In Cursor: **Settings → MCP**, toggle **playwright** off then on (or reload the window) so it reconnects through the proxy.
2. From the project root, start the dashboard:

```text
uv run cim dashboard --db logs/cursor-playwright.sqlite --port 8765
```

3. Open http://127.0.0.1:8765
4. In a Cursor chat, use Playwright tools until **one tool** has **more than 30** calls (warm-up). The page should show calls stacking and **Record is safe**.
5. Then make **one unusual call** for that tool (new argument shape, a new value class such as a private IP in an argument, a first error, or a much larger result). Confirm a behaviour warning on the dashboard.

## Checks

- Store file grows: `logs/cursor-playwright.sqlite`
- `cim verify-chain --db logs/cursor-playwright.sqlite` passes while nothing was edited by hand
- After warm-up + unusual use: alert code `mcp_behaviour_drift`

## URL MCPs (path 2)

Roma, Axiom, Supabase, Vercel, Graphiti use **URL** MCP through `cim http-gateway`
(`docs/setup/cursor-http-mcp-gateway.md`, store `logs/cursor-http.sqlite`). HexStrike
on VM-MON remains the lab demo for the graded stdio path.
