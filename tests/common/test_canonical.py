"""Canonical-JSON hashing rule tests (T-02)."""

from __future__ import annotations

import pytest

from cim.common.schema.canonical import canonical_json


def test_sorted_compact_utf8() -> None:
    assert canonical_json({"b": 1, "a": [True, None, "é"]}) == '{"a":[true,null,"é"],"b":1}'


def test_key_order_irrelevant() -> None:
    assert canonical_json({"a": 1, "b": 2}) == canonical_json({"b": 2, "a": 1})


@pytest.mark.parametrize("bad", [1.5, float("nan"), {"x": [1, 2.0]}])
def test_floats_rejected(bad: object) -> None:
    with pytest.raises(ValueError):
        canonical_json(bad)


def test_non_string_key_rejected() -> None:
    with pytest.raises(ValueError):
        canonical_json({1: "a"})
