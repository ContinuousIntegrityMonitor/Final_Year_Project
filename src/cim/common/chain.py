"""Hash-chain rule for the baseline store (T-06).

record_hash = SHA256(prev_hash || kind || canonical_json(payload))
"""

from __future__ import annotations

import hashlib

GENESIS_HASH = "0" * 64


def compute_record_hash(prev_hash: str, kind: str, payload_canonical: str) -> str:
    """Return the hex digest that links one store record to the previous one."""
    material = f"{prev_hash}{kind}{payload_canonical}".encode()
    return hashlib.sha256(material).hexdigest()
