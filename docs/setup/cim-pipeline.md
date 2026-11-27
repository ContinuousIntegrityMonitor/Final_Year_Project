# Running the CIM pipeline (T-13)

How to install CIM on one Linux machine, point it at the skills and MCP servers to watch, keep
it running, and read what it found. This is the setup for VM-MON (built on Fasih's machine for
the December demo, week of 14 Dec), and it works the same on a laptop.

Design: [`docs/T13_PIPELINE_DESIGN.md`](../T13_PIPELINE_DESIGN.md). The acceptance test that runs
these steps end to end is `tests/sys/test_t13_pipeline.py`.

## 1. What runs

| Process | What it does | Who starts it |
|---|---|---|
| `cim watch` | Supervises the collectors below, restarts them, records each restart | You, or systemd |
| skills watcher | Notices any change to an installed skill's files (T-08, T-10) | `cim watch` |
| HTTP gateway | Sits in front of URL MCP servers and records their calls (T-16b) | `cim watch`, if `[mcp.gateway]` is set |
| `cim proxy` | Sits in front of one stdio MCP server for one client session | The agent client (Cursor, Claude, ...) |
| `cim skills exec` | Runs one skill helper traced in its own scope, and records what it did | The agent harness |

Everything writes to one hash-chained store (default `logs/cim-store.sqlite`). Runtime state that
is not evidence (heartbeats, session files, `watch.json`) lives next to it in
`logs/cim-store.sqlite.run/`.

## 2. Requirements

- Linux with a systemd **user** session (`systemctl --user status` works). Each helper run gets
  its own cgroup scope.
- `strace`, allowed to trace a child of your user (the Fedora and Ubuntu defaults allow it).
- Python 3.12 and [uv](https://docs.astral.sh/uv/).

## 3. Install

```bash
git clone https://github.com/ContinuousIntegrityMonitor/Final_Year_Project.git cim
cd cim
scripts/bootstrap.sh        # or: uv sync --all-extras
uv run cim version
```

`uv sync` without `--all-extras` leaves out the test tools (pytest, ruff, mypy); CIM itself runs
either way.

## 4. Configure: `cim.toml`

```bash
uv run cim init --origin vm-mon --skill-root /opt/skills      # writes ./cim.toml
```

Then edit `cim.toml`. Every key is optional; [`cim.example.toml`](../../cim.example.toml) lists
them all with their defaults. The usual additions:

```toml
[mcp.servers.hexstrike]                # one table per stdio MCP server
root = "/opt/mcp/hexstrike"
tools_list = "corpora/mcp/tools_list.json"   # optional: offline inventory and sweep
minimum_tools = 150

[mcp.gateway]                          # optional: URL MCP servers through the gateway
port = 8877

[[mcp.gateway.routes]]
id = "graphiti"
upstream = "http://127.0.0.1:8000/mcp/"
# authorization_env = "CIM_MCP_AUTH_GRAPHITI"   # the NAME of the variable holding the token
```

Rules:

- **Where it is found:** `--config` > `$CIM_CONFIG` > `./cim.toml` > `~/.config/cim/cim.toml`.
- **What wins:** flag > environment variable > file > default.
- **No secrets in the file.** A key named like a token, secret or password is refused. Tokens
  stay in the environment: `CIM_HTTP_GATEWAY_TOKEN`, and each route's `authorization_env`.
- Relative paths are taken from the file's own folder.

## 5. First inventory

```bash
uv run cim inventory      # baselines every skill under the roots; pins each server with a tools_list
uv run cim status         # exit 0: chain ok, nothing found yet
```

A server without a `tools_list` is pinned the first time a client lists its tools through
`cim proxy`.

## 6. Keep it running: `cim watch`

```bash
uv run cim watch          # in the foreground; Ctrl-C stops it and its children
```

On VM-MON, run it under systemd so it starts at login and comes back if it dies:

```bash
mkdir -p ~/.config/systemd/user
uv run cim init --systemd > ~/.config/systemd/user/cim-watch.service   # keeps an existing cim.toml
systemctl --user daemon-reload
systemctl --user enable --now cim-watch
journalctl --user -u cim-watch -f
```

What `cim watch` does:

- **Restarts:** a child that exits, or whose heartbeat stops for three `heartbeat_s`, is
  restarted after 1, 2, 4 ... seconds (up to `backoff_max_s`).
- **Give-up:** after `max_restarts` restarts in 10 minutes it gives up on that child, records
  it, and keeps the others running.
- **Records:** every restart is a `collector_restarted` record in the chain, and every give-up a
  `collector_failed` record.
- **Gaps:** an edit made while the watcher is down is caught by its first sweep after the
  restart, and recorded once, timestamped at that sweep. An edit made **and undone** during the
  gap leaves no trace; the restart record shows that the gap existed.

## 7. Connect the agents

**Stdio MCP servers:** in the client's MCP config, run the server through `cim proxy`:

```json
{
  "mcpServers": {
    "hexstrike": {
      "command": "/path/to/cim/.venv/bin/cim",
      "args": ["proxy", "--config", "/path/to/cim.toml", "--server", "hexstrike",
               "--", "python3", "/opt/mcp/hexstrike/hexstrike_mcp.py"]
    }
  }
}
```

The proxy passes the MCP stream through unchanged, never writes to stdout itself, and registers
a session file while the session is open.

**URL MCP servers:** point the client at `http://127.0.0.1:8877/s/<route id>` instead of the
real URL (see [`cursor-http-mcp-gateway.md`](cursor-http-mcp-gateway.md)).

**Skills:** the agent harness runs a helper through CIM instead of directly:

```bash
uv run cim skills exec --db logs/cim-store.sqlite --root /opt/skills \
  word-count -- scripts/count.py sample.txt
```

The helper's stdout comes back byte for byte, its stderr and exit status are passed through, and
CIM's own notes (including a behaviour alert) go to stderr after the helper's. It refuses a
script outside the skill (exit 126) or an unknown skill (127), and does not run the helper at all
without a cgroup scope and strace (125).

## 8. Read what it found

```bash
uv run cim status                 # one screen; --json for scripts
uv run cim events --last 50       # one line per record; --follow, --side, --kind, --since
uv run cim dashboard --db logs/cim-store.sqlite      # http://127.0.0.1:8765
uv run cim verify-chain           # note the tip and count it prints somewhere outside the store
```

`cim status` exit codes:

| Exit | Meaning |
|---|---|
| 0 | Chain verifies and nothing was found |
| 1 | The chain is broken, or there is a changed artefact, a behaviour alert, a monitor event or a capture fault |
| 2 | The monitor is not running (`cim watch` ran for this store and has stopped; or never ran, with `--require-watch`), or there is no store |

What each finding means:

- **Changed artefact:** a skill's files or an MCP server's tools differ from their baseline. One
  rug pull or one edited skill is one changed artefact, listed with all its changes.
- **Behaviour alert:** a skill run or tool call left the pattern learned over its first 30 runs
  (T-16): a never-seen program, path, destination or value class, or a count far above normal.
- **Monitor event:** `cim watch` restarted a collector, or gave up on it.
- **Capture fault:** something could not be recorded or scored. The run itself is kept.
- **Learning:** skills and tools with fewer than 30 runs or calls. They cannot raise behaviour
  alerts yet.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `status` exits 2, `cim watch NOT RUNNING` | The supervisor stopped | `systemctl --user status cim-watch`; `journalctl --user -u cim-watch` |
| `collector_failed (gave_up)` | A collector kept dying | Its error is in the `cim watch` log; fix it, then restart `cim watch` |
| `ended without closing` under sessions | A proxy or exec process was killed | Nothing to do: the file only marks the gap; delete it from `*.run/sessions/` when done |
| `exec` exits 125 | No systemd user session, or strace missing or blocked | Run from a login session; install strace; check `kernel.yama.ptrace_scope` |
| `http-gateway` refuses to start | A route sets `authorization_env` but `CIM_HTTP_GATEWAY_TOKEN` is unset (H1) | Export `CIM_HTTP_GATEWAY_TOKEN`, then restart |
| `cim: … secrets do not belong in the config file` | A token went into `cim.toml` | Move it to an environment variable |

## 10. Check the whole pipeline

```bash
uv run pytest tests/sys/test_t13_pipeline.py -v
```

In about 10 seconds the test runs: bootstrap into an empty folder, `cim watch`, 10 benign
operations (all clean), one tampered skill (exactly one finding), and a watcher killed with
`-9` (back within seconds, one restart record, the edit made in the gap recorded once).
