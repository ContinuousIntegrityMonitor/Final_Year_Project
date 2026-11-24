"""Stand-in for Hamza's scripts/_live_t16b_http_warmup.py (not in git: scripts/_* is ignored).

Starts a fake Streamable-HTTP MCP upstream and a real `cim http-gateway` process, then:
  1. warm-up + unusual call -> expect one mcp_behaviour_drift alert (private_ip)
  2. refusals -> expect 401 for missing token, bad Origin, bad Host; upstream not reached
  3. extra angles (each prints what happened; they are probes, not pass/fail gates):
     a. no gateway token + Origin: null + text/plain body -> is the stored Bearer attached?
     b. %2e%2e in the path -> what path does the upstream receive?
     c. long-lived SSE stream -> does the first event reach the client before the stream ends?
     d. two clients reusing the same JSON-RPC id at once -> are both calls recorded?

usage: uv run python scripts/live_t16b_http.py . <empty-dir>
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SECRET = "not-a-real-bearer"
GW_TOKEN = "test-gateway-token"
seen: list[dict[str, str | None]] = []


class Upstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _send(self, payload: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        seen.append({"method": "GET", "path": self.path, "auth": self.headers.get("Authorization")})
        if self.path.endswith("/stream"):
            # Long-lived server->client stream: one event now, the end 6 s later.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b'event: message\ndata: {"jsonrpc":"2.0","method":"ping"}\n\n')
            self.wfile.flush()
            time.sleep(6)
            self.close_connection = True
            return
        self._send(b"{}", "application/json")

    def do_POST(self) -> None:  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        seen.append(
            {"method": "POST", "path": self.path, "auth": self.headers.get("Authorization")}
        )
        body = json.loads(raw.decode())
        mid, method = body.get("id"), body.get("method")
        if method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Echo",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                        },
                    }
                ]
            }
            self._send(
                json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}).encode(),
                "application/json",
            )
            return
        if method == "tools/call":
            text = body["params"]["arguments"].get("text", "")
            if text == "slow":
                time.sleep(1.5)
            data = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {"content": [{"type": "text", "text": text}]},
                }
            )
            self._send(f"event: message\ndata: {data}\n\n".encode(), "text/event-stream")
            return
        self._send(
            json.dumps(
                {"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": "2025-03-26"}}
            ).encode(),
            "application/json",
        )


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def post(port: int, path: str, body: dict | str, headers: dict[str, str]) -> tuple[int, bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = body if isinstance(body, str) else json.dumps(body)
    conn.request("POST", path, body=data.encode(), headers=headers)
    resp = conn.getresponse()
    out = resp.status, resp.read()
    conn.close()
    return out


def start_gateway(
    repo: Path, cfg: Path, db: Path, port: int, token: str | None
) -> subprocess.Popen:
    env = {**os.environ, "CIM_MCP_AUTH_FAKE": SECRET}
    env.pop("CIM_HTTP_GATEWAY_TOKEN", None)
    if token:
        env["CIM_HTTP_GATEWAY_TOKEN"] = token
    bindir = "Scripts" if os.name == "nt" else "bin"
    cim = repo / ".venv" / bindir / ("cim.exe" if os.name == "nt" else "cim")
    proc = subprocess.Popen(
        [
            str(cim),
            "http-gateway",
            "--config",
            str(cfg),
            "--db",
            str(db),
            "--port",
            str(port),
        ],
        env=env,
        cwd=repo,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            return proc
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("gateway did not start")


def stop(proc: subprocess.Popen) -> str:
    proc.send_signal(signal.SIGINT)
    try:
        _, err = proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        _, err = proc.communicate()
    return err


def records(db: Path) -> list[tuple[str, dict]]:
    con = sqlite3.connect(db)
    rows = con.execute("SELECT kind, payload FROM record ORDER BY id").fetchall()
    con.close()
    return [(k, json.loads(p)) for k, p in rows]


def main(repo: Path, out: Path) -> int:
    up = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    upstream = f"http://127.0.0.1:{up.server_address[1]}/mcp"
    cfg = out / "gw.json"
    cfg.write_text(
        json.dumps(
            {
                "routes": [
                    {"id": "fake", "upstream": upstream, "authorization_env": "CIM_MCP_AUTH_FAKE"}
                ]
            }
        )
    )
    failures: list[str] = []

    # ---- 1 + 2: token on -------------------------------------------------------------
    db = out / "http.sqlite"
    port = free_port()
    gw = start_gateway(repo, cfg, db, port, GW_TOKEN)
    ok_h = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "X-CIM-Gateway-Token": GW_TOKEN,
    }
    s, _ = post(
        port, "/s/fake", {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}, ok_h
    )
    s2, b2 = post(port, "/s/fake", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, ok_h)
    print("initialize", s, "tools/list", s2, json.loads(b2)["result"]["tools"][0]["name"])
    for i in range(35):
        s, b = post(
            port,
            "/s/fake",
            {
                "jsonrpc": "2.0",
                "id": 10 + i,
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {"text": f"note {i}"}},
            },
            ok_h,
        )
        assert s == 200 and b"note" in b, (s, b)
    s, b = post(
        port,
        "/s/fake",
        {
            "jsonrpc": "2.0",
            "id": 99,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "http://192.168.1.10/admin"}},
        },
        ok_h,
    )
    print("unusual call", s)
    before = len(seen)
    refusals = {
        "missing token": {"Content-Type": "application/json"},
        "wrong token": {"Content-Type": "application/json", "X-CIM-Gateway-Token": "nope"},
        "bad Origin": {**ok_h, "Origin": "https://evil.example"},
        "bad Host": {**ok_h, "Host": "evil.example"},
    }
    for name, hdr in refusals.items():
        s, b = post(
            port,
            "/s/fake",
            {
                "jsonrpc": "2.0",
                "id": 500,
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {"text": "x"}},
            },
            hdr,
        )
        print(f"refusal {name}: {s}")
        if s != 401:
            failures.append(f"refusal {name} gave {s}")
    if len(seen) != before:
        failures.append("a refused request reached the upstream")
    print("upstream reached by refused requests:", len(seen) - before)
    err = stop(gw)
    recs = records(db)
    kinds: dict[str, int] = {}
    for k, _ in recs:
        kinds[k] = kinds.get(k, 0) + 1
    alerts = [p for k, p in recs if k == "alert"]
    print("records by kind:", kinds)
    for a in alerts:
        print("alert:", json.dumps(a))
    drift = [a for a in alerts if a.get("code") == "mcp_behaviour_drift"]
    if not (len(drift) == 1 and "private_ip" in drift[0]["detail"]):
        failures.append("expected exactly one private_ip behaviour alert")
    raw = db.read_bytes() + b"".join(p.read_bytes() for p in out.glob("http.sqlite-*"))
    print(
        "bearer in store files:", SECRET.encode() in raw, "| bearer in gateway log:", SECRET in err
    )
    if SECRET.encode() in raw or SECRET in err:
        failures.append("bearer leaked")
    print(
        "upstream saw bearer on accepted calls:",
        all(x["auth"] == f"Bearer {SECRET}" for x in seen[:before]),
    )

    # ---- 3: probes (H1: gateway with authorization_env refuses to start without token) --
    db2 = out / "http-probe.sqlite"
    port2 = free_port()
    env_probe = os.environ.copy()
    env_probe["CIM_MCP_AUTH_FAKE"] = SECRET
    env_probe.pop("CIM_HTTP_GATEWAY_TOKEN", None)
    bindir = "Scripts" if os.name == "nt" else "bin"
    cim_bin = repo / ".venv" / bindir / ("cim.exe" if os.name == "nt" else "cim")
    proc = subprocess.Popen(
        [
            str(cim_bin),
            "http-gateway",
            "--config",
            str(cfg),
            "--db",
            str(db2),
            "--host",
            "127.0.0.1",
            "--port",
            str(port2),
        ],
        cwd=str(repo),
        env=env_probe,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _, err_probe = proc.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        _, err_probe = proc.communicate()
        failures.append("H1: gateway without token should have exited")
        print("probe a (H1 refuse start): FAIL timed out")
    else:
        print(
            f"probe a (H1 refuse start without CIM_HTTP_GATEWAY_TOKEN): "
            f"exit={proc.returncode} err={err_probe.strip()[:160]!r}"
        )
        if proc.returncode == 0 or "CIM_HTTP_GATEWAY_TOKEN" not in err_probe:
            failures.append("H1: expected refuse-to-start mentioning CIM_HTTP_GATEWAY_TOKEN")

    # b–d still need a running gateway; use the token.
    port3 = free_port()
    gw2 = start_gateway(repo, cfg, db2, port3, GW_TOKEN)
    seen.clear()
    s, _ = post(
        port3,
        "/s/fake/%2e%2e/admin",
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        {
            "Content-Type": "application/json",
            "X-CIM-Gateway-Token": GW_TOKEN,
        },
    )
    print(
        f"probe b (%2e%2e): status {s}, upstream path={seen[-1]['path'] if seen else None!r}, "
        f"auth attached={bool(seen and seen[-1]['auth'])}"
    )
    conn = http.client.HTTPConnection("127.0.0.1", port3, timeout=10)
    t0 = time.monotonic()
    conn.request(
        "GET",
        "/s/fake/stream",
        headers={"Accept": "text/event-stream", "X-CIM-Gateway-Token": GW_TOKEN},
    )
    resp = conn.getresponse()
    first = resp.read(20)
    print(
        f"probe c (SSE): first bytes after {time.monotonic() - t0:.1f}s "
        f"(upstream sent its first event at ~0s and closed at ~6s): {first!r}"
    )
    conn.close()
    n_before = sum(1 for k, _ in records(db2) if k == "behaviour") if db2.exists() else 0

    def call(text: str) -> None:
        post(
            port3,
            "/s/fake",
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "echo", "arguments": {"text": text}},
            },
            {
                "Content-Type": "application/json",
                "X-CIM-Gateway-Token": GW_TOKEN,
            },
        )

    ta = threading.Thread(target=call, args=("slow",))
    ta.start()
    time.sleep(0.3)
    call("fast")
    ta.join()
    stop(gw2)
    n_after = sum(1 for k, _ in records(db2) if k == "behaviour")
    print(
        "probe d (two clients, id 7 each): calls made 2, "
        f"behaviour records added {n_after - n_before}"
    )

    up.shutdown()
    print("RESULT:", "PASS" if not failures else "FAIL " + "; ".join(failures))
    return 0 if not failures else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", type=Path, help="repository root (has .venv/)")
    parser.add_argument("outdir", type=Path, help="empty directory for config and stores")
    args = parser.parse_args()
    sys.exit(main(args.repo.resolve(), args.outdir.resolve()))
