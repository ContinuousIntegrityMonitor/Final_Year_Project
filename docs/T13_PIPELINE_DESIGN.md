# T-13 pipeline and `cim` CLI: design note

From Fasih (T-13 lead), for Hamza. **A proposal: no code is written until you agree it.** It changes `src/cim/cli.py`, which you wrote, and how your proxy and gateway get their settings. Your answers to section 10 decide the implementation PRs.

## 1. What the plan asks

> Single `cim` CLI: inventory / watch / status / events / verify-chain; one config file; both collectors run as supervised processes with a watchdog. This is the joint integration point.
>
> Acceptance: clean-machine bootstrap; 10 scripted benign operations produce a correct inventory and zero alerts; one tampered artefact produces exactly one alert; a killed collector is restarted by the watchdog.

C5 for December: "`cim status` shows inventory, events, alerts; chain verification passes."

## 2. Where we are

| Plan item | Today |
|---|---|
| One CLI | Two. `cim` (Typer: `inventory`, `proxy`, `http-gateway`, `sweep`, `envelope`, `verify-chain`, `dashboard`; MCP only) and `python -m cim.skills` (argparse: `corpus`, `inventory`, `sweep`, `watch`, `observe`, `envelope`, `board`, `attack`). |
| `status`, `events` | `cim status` is a stub; no `events`. |
| One config file | None. Settings come from eight fixed `CIM_*` variables (plus the `CIM_MCP_AUTH_*` names gateway routes point at), flags with MCP-specific defaults (`--server-id hexstrike`, `--origin vm-mon`, `--minimum 150`), and `config/cursor-http-gateway.json`. That file can hold `access_token`, a secret in a file. `common/config.py` is a stub. |
| Supervised collectors, watchdog | Nothing supervises anything. |
| One store for both sides | Done: several writers share one store since PR #11. |

## 3. What is a "collector": the process model

The plan pictured two daemons. What we built has two kinds of process on each side:

| | Long-running daemon | Wrapper, one per session or run |
|---|---|---|
| MCP | `cim http-gateway` | `cim proxy`, started by the agent client (Cursor) for each stdio server session |
| Skills | `cim skills watch` (integrity) | the behaviour collector, which runs inside each helper invocation (`strace -f` in the run's cgroup scope, T-11) |

The wrappers cannot be restarted by CIM. A proxy belongs to the client's session: if it dies, the client decides whether to reconnect. A skill run is over when it is over. So the proposal is:

- **The watchdog supervises the daemons:** it starts them, notices an exit or a hang, restarts them with backoff, and records each restart.
- **The watchdog tracks the wrappers:** each wrapper registers when it starts and removes itself when it ends. `cim status` shows the live ones, and any that ended without removing themselves.

This is a deviation from the plan's wording, and it follows from T-11's own deviation (a trace per invocation, not `/proc` polling). It goes in the T-13 progress file.

**A gap in the watcher costs no integrity evidence.** The watcher sweeps as soon as it starts, so a restart catches anything changed while it was down. Checked with a throwaway supervisor (2026-11-24):

```
 5.5s  edit 1 while running          -> 1 integrity record
 5.5s  watcher killed with -9; edit 2 while it is down
 6.5s  restarted (1.0 s after the kill)
 9.5s  2 integrity records: word-count modify SKILL.md, dir-tree modify SKILL.md
13.5s  after two more sweeps: still 2 (no repeats)
```

There are two limits, for the threat model. A change made during the gap is timestamped at the restart, not when it happened. And a change made *and undone* during the gap leaves no trace, because the sweep compares hashes. The restart record (section 6) shows the gap exists.

## 4. One config file: `cim.toml`

TOML, read with the standard library's `tomllib`. It allows comments, which the operator needs; JSON does not.

```toml
[store]
path = "logs/cim-store.sqlite"
origin = "vm-mon"                      # the host name recorded with every artefact

[skills]
roots = ["/opt/skills"]                # CIM_SKILL_ROOTS still overrides
sweep_interval_s = 60
inotify = true

[mcp.servers.hexstrike]                # `cim proxy --server hexstrike -- <cmd>` reads this
root = "/opt/mcp/hexstrike"
tools_list = "corpora/mcp/tools_list.json"   # optional: offline `cim inventory` / `cim sweep`
minimum_tools = 150

[mcp.gateway]                          # optional; `cim watch` starts the gateway when present
host = "127.0.0.1"
port = 8877

[[mcp.gateway.routes]]
id = "graphiti"
upstream = "http://127.0.0.1:8000/mcp/"
# authorization_env = "CIM_MCP_AUTH_GRAPHITI"   # the NAME of a variable, never the token

[dashboard]
port = 8765

[scorer]                               # T-16 defaults (docs/T16_SHARED_SCORER_DESIGN.md)
threshold_milli = 4000

[watchdog]
heartbeat_s = 10
backoff_max_s = 60
max_restarts = 5                       # in 10 minutes; then give up, record it, keep the rest running
```

**Rules:**
- **Where it is found:** `--config` > `CIM_CONFIG` > `./cim.toml` > `~/.config/cim/cim.toml`. With no file, today's defaults apply, so nothing breaks.
- **What wins:** flag > environment variable > file > default. Every existing `CIM_*` variable keeps working.
- **No secrets in the file:** the loader refuses a key named like `token`, `secret` or `password`. Secrets stay in the environment. That removes `access_token` from the gateway config (test report H1).
- **The gateway's JSON:** `config/cursor-http-gateway.json` is still read if `[mcp.gateway]` is absent, with a note to move it. The tracked file becomes `cim.example.toml` with the personal routes taken out (test report L5).
- **In code:** a frozen dataclass in `common/config.py`, built once and passed down, so no module reads the environment on its own.

A Cursor entry then becomes `cim proxy --config /path/cim.toml --server hexstrike -- <server command>`, instead of four environment variables.

## 5. The command map

| Command | What it does | Change |
|---|---|---|
| `cim init` | Writes a starter `cim.toml` (skill roots, store path, origin) | new |
| `cim inventory` | Skills: baselines for every root. MCP: inventory + pin for each server with a `tools_list`. One line per side | both sides (today MCP only) |
| `cim sweep` | Skills sweep and MCP sweep against the pins | both sides |
| `cim watch` | The supervisor: starts the skills watcher and, if configured, the gateway; restarts them; Ctrl-C stops all | new (section 6) |
| `cim status` | C5: store, collectors, inventory, findings, learning state. `--json`. Exit 0 clean, 1 findings or broken chain, 2 monitor not running | new (section 7) |
| `cim events` | One line per record, newest last: `--since`, `--kind`, `--side`, `--follow`, `--json` | new |
| `cim verify-chain` | As today | none |
| `cim proxy`, `cim http-gateway` | As today, plus `--config` / `--server` | config |
| `cim envelope` | Both sides' behaviour profiles | both sides |
| `cim dashboard` | As today (with the U1 wiring, PR #21) | none |
| `cim skills …` | The skills-only tools: `corpus`, `observe`, `exec`, `attack`, `board` | moved from `python -m cim.skills`, which stays as an alias |

`cim skills exec <skill> -- <script> [args]` is new: the skills wrapper an agent harness calls to run a helper. It runs the helper in its scope under the collector, records the behaviour, and (once the scorer exists) scores it. It is the skills twin of `cim proxy`.

**Territory.** `cli.py` becomes a thin file at the border. It builds the shared commands and mounts each side's commands from that side's own module: `cim.mcp.cli` (yours) and `cim.skills.cli` (mine). Neither of us then edits the other's commands to add our own. `cim skills` forwards its arguments to the existing argparse entry point, so the skills commands need no rewrite.

## 6. The watchdog (`cim watch`)

- **Children:** built from the config. `cim skills watch` always; `cim http-gateway` when `[mcp.gateway]` exists.
- **Liveness:** two signals.
  - The process exits.
  - Its heartbeat goes stale. Each daemon touches `<store>.run/<name>.heartbeat` every `heartbeat_s`. The watcher after each sweep tick; the gateway from a timer thread, a few lines in your code. A child with no heartbeat for three intervals is treated as hung, killed and restarted.
- **Restart:** backoff 1, 2, 4 … up to `backoff_max_s`. After `max_restarts` in 10 minutes it gives up on that child, records it, and keeps the others running.
- **Wrappers:** `cim proxy` and `cim skills exec` write `<store>.run/sessions/<name>-<pid>.json` at start and delete it at the end. `cim status` lists live ones and reports a file whose process is gone as "ended without closing".
- **What goes in the chain:**
  - `alert` records with codes `collector_restarted` and `collector_failed`. They name the child, its exit code or "hung", and the gap in seconds.
  - Each sits under an artefact of a new type `monitor` (contract v1.1, joint).
  - Heartbeats and session files are runtime state, not evidence. They stay out of the chain, or it would grow by a record every ten seconds.
- **Stop:** SIGTERM to every child, wait 5 s, then SIGKILL. On Windows (your dev machine) `terminate()` is used. The supervisor is plain `subprocess`, so it runs there too.
- **Who watches the watchdog:** on VM-MON, `cim watch` runs as a systemd user unit with `Restart=on-failure`; `cim init --systemd` prints it. If the supervisor itself is down, `cim status` says so (exit code 2). A deliberate kill by code running as the same user (adversary AD3) is not something Phase 1 can prevent: the threat model says so in A5, and T-26 / T-27 take it over.

## 7. `cim status` (C5)

```
store      logs/cim-store.sqlite   chain ok   412 records   tip 3f9c…a1   hash v2
collectors watch running 2h14m · skills-watcher ok (0 restarts) · http-gateway ok
           proxy sessions: hexstrike (pid 4411, 38 min)
inventory  mcp: 1 server, 151 tools   skills: 15
findings   1 changed artefact: skill word-count (modify SKILL.md, 10:42:07)
           0 behaviour alerts   0 monitor events
learning   mcp: 149 tools under 30 calls   skills: 15 under 30 runs
```

- **Findings count changed artefacts, not records.** One rug pull can write several drift records (one per changed field, `mcp/drift.py`), and one skill edit writes one record per file. "One tampered artefact produces exactly one alert" is read as one changed artefact, listed with all its changes. That is also what an operator wants to see.
- **Behaviour alerts** are `alert` records with the drift codes (T-16). **Monitor events** are the watchdog's.
- **Read models:** it reads the store once and reuses each side's read model: `cim.skills.board.skills_board` (PR #21) and an MCP summary from `cim.dashboard.board` / `cim.mcp` (yours). `cim events` uses each side's one-line description: `cim.skills.board.rail_label` and an MCP equivalent.

## 8. Acceptance test

`tests/sys/test_t13_pipeline.py`, marked `sys` so CI runs it. The GitHub runner is a clean Ubuntu machine with `strace` and a systemd user session; the T-11 tracer tests already run there.

| Plan clause | Test |
|---|---|
| Clean-machine bootstrap | CI's fresh checkout + `scripts/bootstrap.sh` steps, then `cim init` into a temp dir and `cim inventory` |
| 10 benign operations → correct inventory, zero alerts | 5 `cim skills exec` runs of corpus helpers + 5 tool calls through `cim proxy` with `tests/mcp/sdk_server.py`. `cim status --json` must show 15 skills, 2 tools, 0 findings, 0 behaviour alerts, 0 monitor events |
| One tampered artefact → exactly one alert | With `cim watch` running, edit one skill file. Within 5 s, `status` shows exactly 1 changed artefact |
| A killed collector is restarted | `kill -9` the skills-watcher child and edit a second skill. Within 3 s it is running again; `status` shows 1 restart and 1 `collector_restarted` event; the second edit is recorded once |

Ten operations are fewer than the 30 warm-up runs, so "zero alerts" here says nothing about the scorer. SYS-08 (100+ runs after warm-up) is the scorer's own test (T-16).

## 9. Work split and order

The window is now (Nov W4 to Dec W1); T-18 rehearsals start the end of Dec W2.

1. **This note agreed** (you, then Fasih).
2. **PR: `common/config.py` loader, `cim.example.toml`, tests.** Fasih; border, both review.
3. **PR: `cli.py` restructure.** Sub-apps, `cim skills`, `cim init`, two-sided `inventory` / `sweep` / `envelope`, `--config`. Fasih writes the shared part; the MCP part of `--config` (proxy, gateway) is yours, or Fasih's if you pre-agree.
4. **PR: `cim status` and `cim events`.** Fasih; the MCP summary and description helpers are yours.
5. **PR: `cim watch` supervisor and heartbeats, plus `cim skills exec` and the session files.** Fasih; the gateway heartbeat and proxy session file are a few lines in your code.
6. **PR: the acceptance test and a runbook** (`docs/setup/cim-pipeline.md`). Fasih.
7. **Contract v1.1:** artefact type `monitor`, codes `collector_restarted` / `collector_failed`. Joint; joins the v1.1 PR.

## 10. Decisions for you

1. One `cim.toml` (TOML), its precedence, and the no-secrets rule, which retires `access_token` in the gateway JSON.
2. The process model in section 3: the watchdog supervises daemons and tracks wrappers.
3. Our own supervisor, run under systemd on VM-MON, rather than systemd units alone. Systemd alone would not record restarts in the chain, and would not run on your Windows machine.
4. Watchdog restarts as `alert` records under a new artefact type `monitor` (contract v1.1).
5. The CLI layout in section 5: side modules register their own commands, `cli.py` is at the border, and the old commands keep working.
6. `cim status` counts changed artefacts as findings, and uses exit codes 0 / 1 / 2.
7. Which of the MCP pieces you take: the `--config` handling in proxy and gateway, the MCP status summary and event descriptions, the gateway heartbeat, the proxy session file.
8. **One store writer** (added 2026-11-24, from ADR-007). In the long run `cim proxy` and `cim skills exec` send their events to one writer that `cim watch` runs, instead of each opening the store. In Phase 2 that writer is the only process running as the `cim` user, which is what lets the store and traces be protected from code running as the operator. For December the wrappers may keep writing directly, as today, as long as each side's writes go through one function that can later become the client.
