"""Stand-in for Hamza's scripts/_live_t16_warmup.py (not in git: scripts/_* is ignored).

Real MCP SDK client -> `cim proxy` -> real MCP SDK server (tests/mcp/sdk_server.py).
Warm up one tool past 30 calls, then send one input holding a private IP.
Expect a `mcp_behaviour_drift` alert naming `private_ip`, and a clean chain.

usage: uv run python scripts/live_t16_stdio.py . <new-db-path>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

from mcp.client.stdio import stdio_client

from mcp import ClientSession, StdioServerParameters


async def main(repo: Path, db: Path) -> int:
    env = {
        **os.environ,
        "CIM_PROXY_SERVER_ID": "sdk-test",
        "CIM_PROXY_ORIGIN": "laptop",
        "CIM_PROXY_ROOT": "tests/mcp/sdk_server.py",
    }
    params = StdioServerParameters(
        command=str(repo / ".venv/bin/cim"),
        args=[
            "proxy",
            "--db",
            str(db),
            "--",
            str(repo / ".venv/bin/python"),
            str(repo / "tests/mcp/sdk_server.py"),
        ],
        env=env,
        cwd=str(repo),
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        print("tools:", [t.name for t in tools.tools])
        for i in range(35):
            out = await session.call_tool("shout", {"text": f"hello number {i}"})
            assert out.content[0].text == f"HELLO NUMBER {i}", out
        out = await session.call_tool("add", {"a": 2, "b": 3})
        print("add ->", out.content[0].text)
        out = await session.call_tool("shout", {"text": "10.0.0.5"})
        print("unusual shout ->", out.content[0].text)
    await asyncio.sleep(0.5)  # proxy writer finishes after the child exits

    con = sqlite3.connect(db)
    rows = con.execute("SELECT kind, payload FROM record ORDER BY id").fetchall()
    obs = con.execute("SELECT COUNT(*) FROM envelope_obs").fetchone()[0]
    con.close()
    kinds: dict[str, int] = {}
    alerts = []
    for kind, payload in rows:
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "alert":
            alerts.append(json.loads(payload))
    print("records by kind:", kinds, "envelope_obs:", obs)
    for a in alerts:
        print("alert:", json.dumps(a))
    drift = [a for a in alerts if a.get("code") == "mcp_behaviour_drift"]
    ok = len(drift) == 1 and "private_ip" in drift[0]["detail"] and kinds.get("behaviour") == 37
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", type=Path, help="repository root (has .venv/)")
    parser.add_argument("db", type=Path, help="new store path; must not exist yet")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.repo.resolve(), args.db.resolve())))
