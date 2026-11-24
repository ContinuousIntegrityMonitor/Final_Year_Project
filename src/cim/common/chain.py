"""Hash-chain rule for the baseline store (T-06 / ADR-006).

Version 1 (legacy stores, verify-only)::

    record_hash = SHA256(prev_hash || kind || payload_canonical)

Version 2 (ADR-006 option 3, every new store)::

    record_hash = SHA256(canonical_json([
        "cim-record/2",
        prev_hash,
        artefact_id,
        artefact_type, artefact_name, artefact_origin,
        kind,
        ts,
        payload_canonical,
    ]))
"""

from __future__ import annotations

import hashlib

from cim.common.schema.canonical import canonical_json

GENESIS_HASH = "0" * 64
HASH_V1 = 1
HASH_V2 = 2
HASH_V2_TAG = "cim-record/2"


def compute_record_hash_v1(prev_hash: str, kind: str, payload_canonical: str) -> str:
    """Legacy formula: covers kind and payload only (S2 gap)."""
    material = f"{prev_hash}{kind}{payload_canonical}".encode()
    return hashlib.sha256(material).hexdigest()


def compute_record_hash(
    prev_hash: str,
    kind: str,
    payload_canonical: str,
    *,
    artefact_id: int,
    artefact_type: str,
    artefact_name: str,
    artefact_origin: str,
    ts: str,
) -> str:
    """ADR-006 v2 formula: also covers ts, artefact_id, and the artefact row."""
    material = canonical_json(
        [
            HASH_V2_TAG,
            prev_hash,
            artefact_id,
            artefact_type,
            artefact_name,
            artefact_origin,
            kind,
            ts,
            payload_canonical,
        ]
    )
    return hashlib.sha256(material.encode()).hexdigest()
