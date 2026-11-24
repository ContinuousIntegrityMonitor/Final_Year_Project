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


@pytest.mark.parametrize("bad", ["\ud800", {"a": ["ok", "x\udfffy"]}, {"k\ud800": 1}])
def test_text_that_cannot_be_utf8_is_rejected_by_name(bad: object) -> None:
    with pytest.raises(ValueError, match="lone surrogate"):
        canonical_json(bad)


def test_everything_canonical_json_accepts_can_be_hashed() -> None:
    canonical_json({"emoji": "\U0001f600", "nul": "\x00", "accent": "é"}).encode("utf-8")
