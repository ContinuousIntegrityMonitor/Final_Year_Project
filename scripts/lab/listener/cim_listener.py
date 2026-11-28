"""CIM lab listener (T-04, plan section 4.6): a stand-in for an exfiltration destination.

Accepts TCP connections on every port in CIM_LISTENER_PORTS, reads what the client sends (up
to 1 MiB, until it closes or stays quiet for 10 s), answers an HTTP request with an empty 200 so
HTTP clients finish cleanly, and appends one JSON line per connection to
$LOGS_DIRECTORY/connections.jsonl: time, port, peer, byte count, sha256 and a short preview.
It never sends anything else and never connects out. Standard library only.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

PORTS = [int(p) for p in os.environ.get("CIM_LISTENER_PORTS", "80 443 4444 8080 9000").split()]
LOG = Path(os.environ.get("LOGS_DIRECTORY", "/var/log/cim-listener")) / "connections.jsonl"
LIMIT = 1 << 20
IDLE_S = 10.0
HTTP_METHODS = (b"GET ", b"POST ", b"PUT ", b"HEAD ", b"PATCH ", b"DELETE ", b"OPTIONS ")


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, port: int) -> None:
    peer = writer.get_extra_info("peername")
    data = bytearray()
    try:
        while len(data) < LIMIT:
            chunk = await asyncio.wait_for(reader.read(65536), IDLE_S)
            if not chunk:
                break
            data.extend(chunk)
            if data.startswith(HTTP_METHODS) and b"\r\n\r\n" in data:
                head, _, body = bytes(data).partition(b"\r\n\r\n")
                length = next(
                    (
                        int(line.split(b":", 1)[1])
                        for line in head.split(b"\r\n")
                        if line.lower().startswith(b"content-length:")
                    ),
                    0,
                )
                if len(body) >= length:
                    writer.write(
                        b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                    )
                    await writer.drain()
                    break
    except (TimeoutError, ConnectionError):
        pass
    finally:
        writer.close()
    entry = {
        "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "port": port,
        "peer": f"{peer[0]}:{peer[1]}" if peer else "",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "preview": bytes(data[:200]).decode("utf-8", "replace"),
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as log:
        log.write(json.dumps(entry) + "\n")
    print(f"{entry['ts']} port {port} from {entry['peer']}: {entry['bytes']} bytes", flush=True)


async def main() -> None:
    servers = [
        await asyncio.start_server(lambda r, w, p=port: handle(r, w, p), "0.0.0.0", port)
        for port in PORTS
    ]
    print(f"cim-listener: listening on {' '.join(map(str, PORTS))}; log {LOG}", flush=True)
    await asyncio.gather(*(server.serve_forever() for server in servers))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
