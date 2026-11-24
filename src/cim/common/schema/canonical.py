"""Canonical JSON for hashing (T-02): sorted keys, no whitespace, UTF-8, no floats.

ADR-006 v2 record hashes pass a JSON array through this helper; see cim.common.chain.
"""

from __future__ import annotations

import json
from typing import Any


def _check_text(text: str, path: str) -> None:
    # JSON can carry a lone surrogate (an escape such as "\ud800"); UTF-8 cannot, so such a
    # string has no bytes to hash. Reject it here, by name, instead of failing at encode time.
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(f"string is not valid Unicode text (lone surrogate): {path}") from None


def _check(obj: Any, path: str = "$") -> None:
    if isinstance(obj, str):
        _check_text(obj, path)
        return
    if obj is None or isinstance(obj, bool | int):
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
            _check_text(key, f"{path} (key)")
            _check(value, f"{path}.{key}")
        return
    raise ValueError(f"unsupported type in hashed payload: {type(obj).__name__} at {path}")


def canonical_json(obj: Any) -> str:
    """Return canonical JSON text. Hash its UTF-8 encoding."""
    _check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
