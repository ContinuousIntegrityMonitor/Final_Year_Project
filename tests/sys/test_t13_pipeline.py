"""T-13 acceptance test: the pipeline end to end (docs/T13_PIPELINE_DESIGN.md, section 8).

Each clause of the plan, and the step that checks it:
- **Clean-machine bootstrap:** CI's fresh checkout and `uv sync --all-extras`
  (scripts/bootstrap.sh), then `cim init` in an empty folder and `cim inventory`.
- **10 scripted benign operations give a correct inventory and zero alerts:** 5
  `cim skills exec` runs of corpus helpers and 5 tool calls through `cim proxy`.
- **One tampered artefact produces exactly one alert:** one skill file edited under `cim watch`.
- **A killed collector is restarted by the watchdog:** `kill -9` the skills watcher and edit
  another skill while it comes back.

Everything runs for real: the `cim` CLI as subprocesses, helpers traced in their own cgroup
scope, the MCP SDK test server behind `cim proxy`, and `cim watch` supervising the skills
watcher. It needs a systemd user session and strace (CI's runner has both) and skips without
them. Ten operations are fewer than the 30-run warm-up, so "zero alerts" here says nothing
about the scorer; that is SYS-08 (T-16).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from cim.skills.collector import tracer_available
from cim.skills.corpus import default_root, load_manifest
from cim.skills.scoped import scope_available

REPO = Path(__file__).resolve().parents[2]
CIM = [sys.executable, "-m", "cim"]
BENIGN = ("word-count", "csv-summary", "date-convert", "json-format", "unit-convert")
TAMPERED = "markdown-toc"  # edited while cim watch runs
EDITED_IN_GAP = "dir-tree"  # edited while the killed watcher is coming back

pytestmark = [
    pytest.mark.sys,
    pytest.mark.skipif(sys.platform != "linux", reason="cgroup scopes and strace are Linux"),
]


def _cim(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [*CIM, *args], cwd=cwd, capture_output=True, text=True, timeout=120, check=False
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"cim {' '.join(args)} -> {result.returncode}\n{result.stdout}\n{result.stderr}"
        )
    return result


def _status(cwd: Path) -> tuple[int, dict[str, Any]]:
    result = _cim("status", "--json", cwd=cwd, check=False)
    return result.returncode, json.loads(result.stdout)


def _wait(what: str, check: Callable[[], bool], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.2)
    raise AssertionError(f"timed out after {timeout:g}s waiting for {what}")


def _integrity(cwd: Path, skill_id: str) -> int:
    events = _cim(
        "events", "--kind", "integrity", "--side", "skills", "--last", "0", "--json", cwd=cwd
    )
    rows = [json.loads(line) for line in events.stdout.splitlines()]
    return sum(row["label"].startswith(f"{skill_id}: ") for row in rows)


async def _five_calls(work: Path) -> None:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "cim",
            "proxy",
            "--server",
            "sdk",
            "--",
            sys.executable,
            str(REPO / "tests/mcp/sdk_server.py"),
        ],
        cwd=str(work),
        env={**os.environ, "CIM_CONFIG": str(work / "cim.toml")},
    )
    with open(os.devnull, "w", encoding="utf-8") as quiet:
        async with (
            stdio_client(params, errlog=quiet) as (read, write),
            ClientSession(read, write) as s,
        ):
            await s.initialize()
            await s.list_tools()
            for n in range(3):
                await s.call_tool("shout", {"text": f"hello {n}"})
            for n in range(2):
                await s.call_tool("add", {"a": n, "b": 2})


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    if not scope_available() or not tracer_available():
        pytest.skip("needs a systemd user session and strace, as `cim skills exec` does")
    # This test makes its own cim.toml; the suite-wide empty CIM_CONFIG must not shadow it.
    monkeypatch.delenv("CIM_CONFIG", raising=False)
    shutil.copytree(default_root(), tmp_path / "skills", ignore=shutil.ignore_patterns("_attacks"))
    return tmp_path


def test_the_pipeline_end_to_end(work: Path) -> None:
    # 1. Clean-machine bootstrap: an empty folder, `cim init`, `cim inventory`.
    _cim("init", "--origin", "ci", "--skill-root", "skills", cwd=work)
    with (work / "cim.toml").open("a", encoding="utf-8") as config:
        config.write(
            '\n[mcp.servers.sdk]\nroot = "tests/mcp/sdk_server.py"\n'
            "\n[watchdog]\nheartbeat_s = 1\nbackoff_max_s = 4\n"
        )
    text = (work / "cim.toml").read_text(encoding="utf-8")
    (work / "cim.toml").write_text(text.replace("[skills]\n", "[skills]\nsweep_interval_s = 2\n"))
    inventory = _cim("inventory", cwd=work)
    assert inventory.stdout.startswith("inventory: skills=15 new_baselines=15 chain=ok")

    watch = subprocess.Popen(
        [*CIM, "watch"], cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
    )
    try:
        _wait(
            "cim watch to report its child",
            lambda: _status(work)[1]["collectors"]["supervised"],
            15,
        )

        # 2. Ten benign operations: 5 traced helper runs, 5 MCP tool calls.
        manifest = load_manifest(work / "skills")
        for skill_id in BENIGN:
            run = manifest[skill_id].runs[0]
            _cim(
                "skills",
                "exec",
                "--db",
                "logs/cim-store.sqlite",
                "--root",
                "skills",
                skill_id,
                "--",
                run.script,
                *run.args,
                cwd=work,
            )
        asyncio.run(_five_calls(work))
        code, shown = _status(work)
        assert shown["inventory"] == {"mcp": {"servers": 1, "tools": 2}, "skills": 15}
        assert shown["findings"] == []
        assert shown["behaviour_alerts"] == {"skills": 0, "mcp": 0}
        assert (shown["monitor_events"], shown["capture_faults"]) == (0, 0)
        assert shown["chain"]["ok"] is True
        assert code == 0 and shown["clean"] is True
        runs = _cim("events", "--kind", "behaviour", "--last", "0", "--json", cwd=work)
        sides = [json.loads(line)["side"] for line in runs.stdout.splitlines()]
        assert (sides.count("skills"), sides.count("mcp")) == (5, 5)

        # 3. One tampered artefact: exactly one finding.
        (work / "skills" / TAMPERED / "SKILL.md").write_text("tampered\n", encoding="utf-8")
        _wait("the edit to be recorded", lambda: len(_status(work)[1]["findings"]) == 1, 10)
        code, shown = _status(work)
        assert code == 1
        assert [f["artefact"] for f in shown["findings"]] == [f"skill {TAMPERED}"]
        assert shown["findings"][0]["changes"] == ["modify SKILL.md"]

        # 4. A killed collector is restarted, and an edit made meanwhile is recorded once.
        child = shown["collectors"]["watch"]["children"][0]
        assert child["name"] == "skills-watcher"
        os.kill(int(child["pid"]), signal.SIGKILL)
        (work / "skills" / EDITED_IN_GAP / "SKILL.md").write_text("edited\n", encoding="utf-8")

        def back() -> bool:
            children = _status(work)[1]["collectors"]["watch"]["children"]
            return children[0]["restarts"] == 1 and children[0]["state"] == "running"

        _wait("the watcher to be restarted", back, 10)
        _wait("the gap edit to be recorded", lambda: _integrity(work, EDITED_IN_GAP) == 1, 10)
        time.sleep(3)  # more sweeps: the edit must not be recorded again
        code, shown = _status(work)
        assert shown["monitor_events"] == 1
        restarts = _cim("events", "--kind", "alert", "--side", "monitor", "--last", "0", cwd=work)
        assert restarts.stdout.count("skills-watcher: collector_restarted (exited)") == 1
        assert _integrity(work, EDITED_IN_GAP) == 1 and _integrity(work, TAMPERED) == 1
        assert sorted(f["artefact"] for f in shown["findings"]) == [
            f"skill {EDITED_IN_GAP}",
            f"skill {TAMPERED}",
        ]
    finally:
        watch.send_signal(signal.SIGTERM)
        try:
            watch.wait(timeout=15)
        except subprocess.TimeoutExpired:
            watch.kill()
            watch.wait()

    # The monitor is down now: status says so, and the chain still verifies.
    stopped = _cim("status", cwd=work, check=False)
    assert stopped.returncode == 2 and "cim watch NOT RUNNING" in stopped.stdout
    assert _cim("verify-chain", cwd=work).stdout.startswith("verify-chain: ok (")
