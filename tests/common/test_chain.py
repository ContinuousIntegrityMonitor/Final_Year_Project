"""Unit tests for hash-chain helper."""

from cim.common.chain import compute_record_hash


def test_compute_record_hash_stable() -> None:
    a = compute_record_hash("0" * 64, "behaviour", '{"ok":true}')
    b = compute_record_hash("0" * 64, "behaviour", '{"ok":true}')
    assert a == b
    assert len(a) == 64


def test_compute_record_hash_changes_on_payload() -> None:
    a = compute_record_hash("0" * 64, "behaviour", '{"ok":true}')
    b = compute_record_hash("0" * 64, "behaviour", '{"ok":false}')
    assert a != b
