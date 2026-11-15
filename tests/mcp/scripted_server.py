"""Line server for proxy tests that answers with exact bytes chosen by the test.

Usage: scripted_server.py <spec.json>, where the spec maps a JSON-RPC method to a list of
raw result texts. The n-th request for a method gets the n-th text (the last one repeats).
The texts are written as they are, so a test can send output no JSON library would produce.
"""

from __future__ import annotations

import json
import sys


def main() -> None:
    with open(sys.argv[1], encoding="utf-8") as handle:
        spec: dict[str, list[str]] = json.load(handle)
    seen: dict[str, int] = {}
    for raw in sys.stdin.buffer:
        try:
            message = json.loads(raw)
        except (ValueError, RecursionError):
            continue
        if not isinstance(message, dict) or "id" not in message:
            continue
        method = str(message.get("method"))
        options = spec.get(method, ["{}"])
        index = seen.get(method, 0)
        seen[method] = index + 1
        result = options[min(index, len(options) - 1)]
        request_id = json.dumps(message["id"])
        sys.stdout.write(f'{{"jsonrpc":"2.0","id":{request_id},"result":{result}}}\n')
        sys.stdout.flush()


if __name__ == "__main__":
    main()
