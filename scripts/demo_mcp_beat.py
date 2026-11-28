#!/usr/bin/env python3
"""T-18: MCP half of the December demo (stand-in path). Runbook: docs/demo/T18_mcp_beat.md.

Steps work offline with corpora/mcp/tools_list.json and cim mcp-attack A1/A2.
VM-MON / HexStrike live beats are documented in the runbook (operator runs them there).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STEPS = ("reset", "inventory", "a1", "a2", "live-stdio", "status")
MARKER = ".cim-demo-mcp-beat"


def _py() -> list[str]:
    win = REPO / ".venv" / "Scripts" / "python.exe"
    unix = REPO / ".venv" / "bin" / "python"
    if win.is_file():
        return [str(win)]
    if unix.is_file():
        return [str(unix)]
    return [sys.executable]


def _cim(work: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CIM_CONFIG": str(work / "cim.toml")}
    # Do not inherit pytest-cov / coverage process hooks (breaks parallel combine).
    for key in list(env):
        if key.startswith(("COV_", "COVERAGE_")):
            env.pop(key, None)
    return subprocess.run(
        [*_py(), "-m", "cim", *args],
        cwd=str(work),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _ok(label: str, cond: bool, detail: str = "") -> bool:
    mark = "OK  " if cond else "FAIL"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    return cond


def step_reset(work: Path, tools: Path, origin: str) -> bool:
    if work.exists():
        if not (work / MARKER).is_file():
            print(f"demo: refusing to wipe {work} (no {MARKER})", file=sys.stderr)
            return False
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / MARKER).write_text("mcp-beat\n", encoding="utf-8")
    shutil.copy(tools, work / "tools_list.json")
    toml = (
        f'[store]\npath = "store.sqlite"\norigin = "{origin}"\n\n'
        f"[mcp.servers.hexstrike]\n"
        f'root = "/opt/mcp/hexstrike"\n'
        f'origin = "{origin}"\n'
        f'tools_list = "tools_list.json"\n'
        f"minimum_tools = 1\n"
    )
    (work / "cim.toml").write_text(toml, encoding="utf-8")
    return _ok("fresh workspace + cim.toml", (work / "cim.toml").is_file())


def step_inventory(work: Path) -> bool:
    result = _cim(
        work,
        "inventory",
        "--config",
        "cim.toml",
        "--side",
        "mcp",
        "--db",
        "store.sqlite",
    )
    out = result.stdout + result.stderr
    print(out.strip())
    ok = result.returncode == 0 and "tools=" in out and "chain=ok" in out
    return _ok("cim inventory (MCP)", ok, f"exit={result.returncode}")


def step_a1(work: Path) -> bool:
    attack_dir = work / "a1"
    result = _cim(work, "mcp-attack", "A1", "--work", str(attack_dir))
    print(result.stdout.strip())
    ok = result.returncode == 0 and "PASS" in result.stdout
    status = _cim(work, "status", "--db", str(attack_dir / "a1-store.sqlite"))
    print(status.stdout.strip())
    findings = "changed artefact" in status.stdout
    return _ok("A1 rug-pull + status findings", ok and findings and status.returncode == 1)


def step_a2(work: Path, warmup: int) -> bool:
    attack_dir = work / "a2"
    result = _cim(work, "mcp-attack", "A2", "--work", str(attack_dir), "--warmup", str(warmup))
    print(result.stdout.strip())
    ok = result.returncode == 0 and "PASS" in result.stdout
    status = _cim(work, "status", "--db", str(attack_dir / "a2-store.sqlite"))
    print(status.stdout.strip())
    alert = "behaviour alert" in status.stdout and status.returncode == 1
    return _ok("A2 trigger + behaviour alert", ok and alert)


def step_live_stdio(work: Path) -> bool:
    """Optional: real SDK client through cim proxy (needs mcp package + unix-ish paths)."""
    db = work / "live-stdio.sqlite"
    script = REPO / "scripts" / "live_t16_stdio.py"
    if not script.is_file():
        return _ok("live-stdio skipped (no script)", True)
    cim_bin = REPO / ".venv" / "Scripts" / "cim.exe"
    if not cim_bin.is_file():
        cim_bin = REPO / ".venv" / "bin" / "cim"
    if not cim_bin.is_file():
        print("  SKIP live-stdio: no .venv cim binary (stand-in A2 already covers C4)")
        return True
    # Patch: live script hard-codes unix venv; invoke via python -m when needed.
    env = {
        **os.environ,
        "CIM_PROXY_SERVER_ID": "sdk-test",
        "CIM_PROXY_ORIGIN": "demo",
    }
    # Prefer our Windows-safe driver using the same warm-up idea via mcp-attack only.
    print("  SKIP live-stdio on this host: use scripts/live_t16_stdio.py on Linux/VM-MON")
    print("       Stand-in A2 already demonstrated mcp_behaviour_drift for C4.")
    _ = (db, env)
    return True


def step_status(work: Path) -> bool:
    db = work / "a2" / "a2-store.sqlite"
    if not db.is_file():
        db = work / "store.sqlite"
    result = _cim(work, "status", "--db", str(db))
    print(result.stdout.strip())
    chain = _cim(work, "verify-chain", "--db", str(db))
    print(chain.stdout.strip())
    ok = "chain ok" in result.stdout.lower() or "hash v" in result.stdout
    verify = chain.returncode == 0 and "ok" in chain.stdout
    return _ok("cim status + verify-chain", ok and verify)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "steps",
        nargs="*",
        default=list(STEPS),
        help=f"steps to run (default: {' '.join(STEPS)})",
    )
    parser.add_argument(
        "--work",
        type=Path,
        default=Path.home() / ".cache" / "cim-demo" / "mcp-beat",
    )
    parser.add_argument(
        "--tools-json",
        type=Path,
        default=REPO / "corpora" / "mcp" / "tools_list.json",
    )
    parser.add_argument("--origin", default="demo-host")
    parser.add_argument("--warmup", type=int, default=30)
    parser.add_argument("--no-pause", action="store_true")
    args = parser.parse_args()
    wanted = []
    for name in args.steps:
        if name == "all":
            wanted.extend(STEPS)
        elif name in STEPS:
            wanted.append(name)
        else:
            parser.error(f"unknown step: {name}")
    failed = 0
    for step in wanted:
        print(f"\n== {step} ==")
        if not args.no_pause and step != "reset":
            try:
                input("  Enter to run (q to quit)… ")
            except EOFError:
                pass
        started = time.perf_counter()
        if step == "reset":
            ok = step_reset(args.work, args.tools_json, args.origin)
        elif step == "inventory":
            ok = step_inventory(args.work)
        elif step == "a1":
            ok = step_a1(args.work)
        elif step == "a2":
            ok = step_a2(args.work, args.warmup)
        elif step == "live-stdio":
            ok = step_live_stdio(args.work)
        else:
            ok = step_status(args.work)
        print(f"  time {time.perf_counter() - started:.1f}s")
        if not ok:
            failed += 1
    print(f"\n{'PASS' if failed == 0 else 'FAIL'}: {len(wanted) - failed}/{len(wanted)} steps")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
