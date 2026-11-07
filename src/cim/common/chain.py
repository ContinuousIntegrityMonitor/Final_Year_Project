"""Hash-chain verifier helpers (implemented in T-06)."""

from __future__ import annotations


def compute_record_hash(prev_hash: str, kind: str, payload_canonical: str) -> str:
    """Placeholder for SHA256(prev_hash || kind || payload)."""
    import hashlib

    material = f"{prev_hash}{kind}{payload_canonical}".encode()
    return hashlib.sha256(material).hexdigest()
