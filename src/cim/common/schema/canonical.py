"""Canonical JSON for hashing (T-02): sorted keys, no whitespace, UTF-8, no floats.

record_hash = SHA256(prev_hash || kind || canonical_json(payload)); see cim.common.chain.
"""

from __future__ import annotations

import json
from typing import Any


def _check(obj: Any, path: str = "$") -> None:
    if obj is None or isinstance(obj, bool | int | str):
        return
    if isinstance(obj, float):
        raise ValueError(f"floats are not allowed in hashed payloads: {path}")
    if isinstance(obj, list | tuple):
        for i, item in enumerate(obj):
            _check(item, f"{path}[{i}]")
        return
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(key, str):
                raise ValueError(f"object keys must be strings: {path}")
            _check(value, f"{path}.{key}")
        return
    raise ValueError(f"unsupported type in hashed payload: {type(obj).__name__} at {path}")


def canonical_json(obj: Any) -> str:
    """Return canonical JSON text. Hash its UTF-8 encoding."""
    _check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
