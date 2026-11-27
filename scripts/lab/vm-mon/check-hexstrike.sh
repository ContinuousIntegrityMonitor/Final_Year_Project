#!/usr/bin/env bash
# T-04 acceptance on VM-MON, run as cim (`scripts/lab/lab.sh vm-mon run cim check-hexstrike.sh`): HexStrike at the pin,
# behind `cim proxy`, lists 150+ tools, and the store records the server with them. Offline.
set -euo pipefail
UV="$HOME/.local/bin/uv"
HS=/opt/mcp/hexstrike
cd "$HS"
.venv/bin/python hexstrike_server.py --port 8888 > /tmp/hexstrike-server.log 2>&1 &
server=$!
trap 'kill "$server" 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do
  curl -fsS -o /dev/null http://127.0.0.1:8888/health 2>/dev/null && break
  sleep 1
done
curl -fsS -o /dev/null http://127.0.0.1:8888/health || { tail -5 /tmp/hexstrike-server.log; exit 1; }
cd "$HOME"
"$UV" run --quiet --project "$HOME/cim" python - <<'PY'
import asyncio, os, sys
from pathlib import Path
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

home = Path.home()
params = StdioServerParameters(
    command=str(home / "cim/.venv/bin/cim"),
    args=["proxy", "--config", str(home / "cim.toml"), "--server", "hexstrike", "--",
          "/opt/mcp/hexstrike/.venv/bin/python", "/opt/mcp/hexstrike/hexstrike_mcp.py",
          "--server", "http://127.0.0.1:8888"],
    cwd=str(home),
)

async def main() -> int:
    with open(os.devnull, "w") as quiet:
        async with stdio_client(params, errlog=quiet) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
    print(f"check-hexstrike: tools/list through cim proxy: {len(tools)} tools")
    return 0 if len(tools) >= 150 else 1

sys.exit(asyncio.run(main()))
PY
sleep 1
"$UV" run --quiet --project "$HOME/cim" cim status --config "$HOME/cim.toml" | sed -n 3p
