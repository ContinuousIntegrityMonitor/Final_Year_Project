# Cursor URL MCPs through CIM HTTP gateway (T-16b)

Path **2**. Cursor points URL MCPs at a local Streamable-HTTP middlebox. The
gateway forwards to the real upstream and records `tools/list` / `tools/call` in
`logs/cursor-http.sqlite` (same store / envelope / T-16 path as stdio).

Stdio Playwright (path 1) stays on `cim proxy` and `logs/cursor-playwright.sqlite`.

## Start the gateway

From the project root:

```text
uv run cim http-gateway --config config/cursor-http-gateway.json
```

Default listen: `http://127.0.0.1:8877`. Routes are under `/s/<id>`:

| Cursor name (mcp.json) | Gateway URL | Upstream |
|------------------------|-------------|----------|
| roma | `http://127.0.0.1:8877/s/roma` | `https://api.roma.app/mcp` |
| axiom | `http://127.0.0.1:8877/s/axiom` | `https://mcp.axiom.co/mcp` |
| supabase | `http://127.0.0.1:8877/s/supabase` | Supabase MCP URL |
| vercel | `http://127.0.0.1:8877/s/vercel` | `https://mcp.vercel.com` |
| graphiti-memory | `http://127.0.0.1:8877/s/graphiti` | `http://127.0.0.1:8000/mcp/` |

**On this PC now:** `graphiti-memory` already points at the gateway. Roma / Axiom / Supabase / Vercel stay on their **direct** HTTPS URLs so Cursor OAuth keeps working. To monitor one of those, set its `CIM_MCP_AUTH_*` env var, change its `url` in `mcp.json` to the gateway URL above, reload that MCP, and keep the gateway running.

## Auth (no secrets in the hash chain)

- Client `Authorization` / `Cookie` headers are **forwarded** and **never** written into the store (only digests of tool args/results).
- Cursor’s built-in OAuth against the **real** host does not run when the MCP URL is localhost. For OAuth servers, set a Bearer token in the environment named in the route’s `authorization_env` (see `config/cursor-http-gateway.json`), e.g. `CIM_MCP_AUTH_ROMA`. The gateway adds `Authorization: Bearer …` only when the client did not send one.
- Graphiti on loopback usually needs no token.

## Dashboard

```text
uv run cim dashboard --db logs/cursor-http.sqlite --port 8766
```

Use a different port from the Playwright dashboard (8765) if both run at once.

## Live T-16 on a URL server

1. Start the gateway, then reload the URL MCP in Cursor Settings.
2. Call one tool **more than 30** times (warm-up).
3. Make one unusual call; confirm a behaviour warning on the HTTP-store dashboard.
4. `uv run cim verify-chain --db logs/cursor-http.sqlite`

## Not replaced

HexStrike on VM-MON through stdio `cim proxy` remains the graded lab path.
