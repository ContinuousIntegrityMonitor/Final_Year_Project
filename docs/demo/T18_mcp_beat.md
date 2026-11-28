# T-18: MCP part of the December demo (runbook)

- **Covers:** Hamza’s MCP beats (C1–C5 MCP half). Skills beats: [`T18_skills_beat.md`](T18_skills_beat.md).
- **Script (stand-in / laptop):** [`scripts/demo_mcp_beat.py`](../../scripts/demo_mcp_beat.py) — inventory from the pinned tools list, then `cim mcp-attack` A1/A2, then status.
- **Live HexStrike on VM-MON:** section 6 (operator on Fasih’s lab; not fully automated here).

## 1. Decisions (Hamza, 2026-11-28)

| Question (skills runbook §2) | Decision |
|---|---|
| One store or two? | **One shared store on stage** for the joint C5 / dashboard view. Solo rehearsals may keep a side-local store (skills script default; this script’s `--work`). |
| Dashboard port | **MCP uses 8765** (default). Skills beat keeps **8766**. |
| Running order | **Accept Fasih’s interleaved minute marks** in `T18_skills_beat.md` §2. |

## 2. What the MCP beat shows

| Step | Audience sees | Criterion |
|---|---|---|
| `reset` | Fresh workspace + `cim.toml` pointing at HexStrike tools list | setup |
| `inventory` | `cim inventory --side mcp` baselines tools + pin | **C1** (MCP) |
| `a1` | Rug-pull: backdoored tools list → schema drift; `cim status` shows **1 changed artefact** | **C3** |
| `a2` | Warm-up then trigger → `mcp_behaviour_drift` | **C4** |
| `live-stdio` | Optional real SDK client through `cim proxy` (Linux / VM-MON) | **C2**-style |
| `status` | `cim status` + `verify-chain` | **C5** |

## 3. Laptop / CI rehearsal (stand-in)

```bash
# from repo root (Windows: .venv\Scripts\python.exe)
uv run python scripts/demo_mcp_beat.py --no-pause all
# or step by step:
uv run python scripts/demo_mcp_beat.py reset inventory a1 a2 status
```

Expect every step `OK` and a final `PASS: N/N steps`.

## 4. How Fasih should review / test this PR

1. `uv sync --all-extras`
2. `uv run ruff check src tests && uv run mypy src`
3. `uv run pytest -m "not lab" -q`  → full suite green
4. Focused:  
   `uv run pytest tests/mcp/test_decision7_config.py tests/mcp/test_mcp_attacks.py tests/mcp/test_dashboard.py tests/mcp/test_dashboard_both_sides.py -q`
5. Demo beat: `uv run python scripts/demo_mcp_beat.py --no-pause all`
6. Polish checks:
   - `cim proxy --help` shows `[mcp.servers.<id>]` and `[store].path` (not truncated markup)
   - `cim mcp-attack A1 --work /tmp/a1` prints `drift records:` (not ambiguous `findings:`)
   - Gateway: start with a tiny `cim.toml` `[mcp.gateway]`, `kill -TERM <pid>`, confirm `<store>.run/http-gateway.heartbeat` is **gone**
7. Dashboard: open a skills-only A3 store — Alerts tile should include skills alerts; connection line should **not** say “Disconnected…” when only monitoring

Reply PASS/FAIL in `CONTEXT.md` (Fasih’s section). **Hamza will merge only after your green signal.**

## 5. Polish included in this ship

- Proxy/gateway Typer help: escape `\[…]` so Rich does not eat section names
- Gateway SIGTERM → same cleanup as Ctrl-C (clears heartbeat)
- A1 report: `drift records:` wording (decision 6)
- Dashboard Alerts tile = MCP alerts + skills summary alerts; monitoring connection copy

## 6. VM-MON live HexStrike (joint, after merge)

On VM-MON as `cim`, with HexStrike at the pin and `cim watch` up:

```bash
# C1 / C2 — inventory already done at provision; live tools/list through proxy is checked by lab scripts
# C3 — swap to a backdoored tools description (or use cim mcp-attack A1 against a work dir on the VM)
cim mcp-attack A1 --work ~/demo/a1
# C4
cim mcp-attack A2 --work ~/demo/a2
# Prefer real HexStrike trigger once the attack pack targets are wired to the live server
cim status --require-watch
cim verify-chain
cim dashboard --db <shared-store>   # port 8765
```

Full HexStrike tool calls against VM-TGT remain the joint dry-run item for presentation week.

## 7. C6

This runbook + `demo_mcp_beat.py` are the MCP half of “demo script committed”. Backup **video** of MCP beats is recorded on VM-MON during the joint rehearsal (skills half already done by Fasih).
