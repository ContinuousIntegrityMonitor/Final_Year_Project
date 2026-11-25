# Fasih verify checklist — Hamza decision‑7 + T‑17 MCP attacks (2026-11-25)

Run these **in order** on a clean checkout of org `main` after Hamza’s decision‑7 / T‑17 ships merge. Sign results back in `CONTEXT.md` (Fasih’s assistant section).

## 0. Bootstrap

```bash
uv sync
uv run ruff check src tests
uv run mypy src
uv run pytest -m "not lab" -q
```

Expect: ruff/mypy clean; full suite green (Hamza’s ships add decision‑7, runtime, A1/A2, dashboard both-sides tests).

## 1. Config loader + two-sided CLI (your stages 1–3, already on main)

```bash
uv run cim init --config /tmp/cim-verify.toml   # or: copy cim.example.toml → ./cim.toml
# Edit [skills].roots and [mcp.servers.<id>].tools_list as needed, then:

uv run cim inventory --config ./cim.toml --skill-root corpora/skills \
  --tools-json corpora/mcp/tools_list.json --server-id hexstrike --db /tmp/cim-verify.sqlite
uv run cim sweep --db /tmp/cim-verify.sqlite --side both \
  --skill-root corpora/skills --tools-json corpora/mcp/tools_list.json --server-id hexstrike
uv run cim status --db /tmp/cim-verify.sqlite
uv run cim events --db /tmp/cim-verify.sqlite --last 20
uv run cim verify-chain --db /tmp/cim-verify.sqlite
```

Expect: inventory both sides; status exit 0 on clean store; chain ok.

## 2. Decision 7 — proxy `--config` / `--server`

```bash
# Minimal cim.toml
cat > /tmp/cim-d7.toml <<'EOF'
[store]
path = "/tmp/cim-d7.sqlite"
origin = "verify"

[mcp.servers.demo]
root = "/tmp/mcp-demo"
origin = "verify"
EOF

# Help must list --config and --server
uv run cim proxy --help

# Session file appears while proxy is up (use any short-lived stdio stand-in you already use
# in live_t16_stdio.py). After the session ends, the file under
# /tmp/cim-d7.sqlite.run/sessions/ must be gone.
```

Expect: `resolve_proxy_config` tests green; live session file create/remove.

## 3. Decision 7 — gateway `cim.toml` vs JSON

```bash
# TOML form (no secrets; token still from env if routes need it)
cat > /tmp/cim-gw.toml <<'EOF'
[store]
path = "/tmp/cim-gw.sqlite"

[mcp.gateway]
host = "127.0.0.1"
port = 8877

[[mcp.gateway.routes]]
id = "demo"
upstream = "http://127.0.0.1:9/mcp/"
EOF

uv run cim http-gateway --config /tmp/cim-gw.toml &
# While running: /tmp/cim-gw.sqlite.run/http-gateway.heartbeat must refresh
# Legacy JSON still works: config/cursor-http-gateway.json
kill %1
```

Expect: auto-detect TOML; heartbeat file while up; cleared on exit.

## 4. T-17 MCP attacks (Hamza A1/A2)

```bash
uv run cim mcp-attack A1 --work /tmp/cim-a1
uv run cim mcp-attack A2 --work /tmp/cim-a2
uv run cim status --db /tmp/cim-a1/a1-store.sqlite   # findings ≥ 1, exit 1
uv run cim status --db /tmp/cim-a2/a2-store.sqlite   # behaviour alert ≥ 1, exit 1
```

Expect: both print `PASS`.

## 5. Skills attacks (your A3/A4) — still green with shared scorer

```bash
uv run python -m cim.skills attack A3 --work /tmp/cim-a3
uv run python -m cim.skills attack A4 --work /tmp/cim-a4
```

Expect: A3 PASS with `skill_behaviour_drift`; A4 PASS with no behaviour alert.

## 6. Dashboard (chosen board: MCP + Skills panels, U1)

The live dashboard is `cim dashboard` → `cim.dashboard` (HTML + `/api/board`). Panels: **MCP** (tools, calls, schema changes, alerts) and **Skills** (installed / healthy / learning / warning).

```bash
# Build a store with both sides (or reuse /tmp/cim-verify.sqlite after inventory)
uv run cim dashboard --db /tmp/cim-verify.sqlite --once | tee /tmp/dash.txt
# Check: send_email or hexstrike tools AND a skills name (e.g. word-count) appear

uv run cim dashboard --db /tmp/cim-verify.sqlite --host 127.0.0.1 --port 8765
# Browser: http://127.0.0.1:8765/  → MCP panel + Skills panel
# curl -s http://127.0.0.1:8765/api/board | python -m json.tool
# Check JSON keys: tools, calls, changes, alerts, patterns, skills.summary
```

Also run the automated coverage:

```bash
uv run pytest tests/mcp/test_dashboard.py tests/mcp/test_dashboard_both_sides.py \
  tests/skills/test_skills_board.py -q
```

Expect: both panels populated; chain_ok true; A1 store shows schema changes; A2 store shows alert evidence.

## 7. Live stand-in scripts (optional but wanted before Dec lab)

```bash
uv run python scripts/live_t16_stdio.py
# Windows: use .venv/Scripts/python
uv run cim status --db <store from script>   # 1 behaviour alert, exit 1
```

## 8. What you still own (do not wait on Hamza for these)

| Item | Notes |
|------|--------|
| T-13 stage 4 `cim watch` | Consume `*.heartbeat` + `sessions/*.json` Hamza already writes |
| T-13 stage 5 | `tests/sys/test_t13_pipeline.py` + `docs/setup/cim-pipeline.md` |
| VM-MON build | Demo week of 14 Dec on your machine |
| Joint live HexStrike C2–C4 | After VM-MON |

## Decision 7 answers (Hamza, locked 2026-11-25)

1. **`[mcp.servers.<id>]` keys accepted as designed:** `root`, `origin`, `tools_list`, `minimum_tools`.
2. **`[mcp.gateway]` keys accepted:** `host`, `port`, `routes[]` with `id`, `upstream`, `origin`, `root`, `authorization_env`.
3. **`--config` clash:** auto-detect — `.toml` / leading `[` → `cim.toml`; else legacy JSON. Same flag name everywhere.
4. **Precedence:** flag > `CIM_PROXY_*` / `CIM_HTTP_GATEWAY_TOKEN` > file > default.
5. **Session + heartbeat paths:** `<store>.run/sessions/proxy-<pid>.json`, `<store>.run/http-gateway.heartbeat`.
