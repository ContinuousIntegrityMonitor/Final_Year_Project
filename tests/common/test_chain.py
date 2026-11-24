"""Unit tests for hash-chain helper (ADR-006 v2 + legacy v1)."""

from cim.common.chain import compute_record_hash, compute_record_hash_v1


def test_compute_record_hash_v2_stable() -> None:
    kwargs = {
        "artefact_id": 1,
        "artefact_type": "mcp_tool",
        "artefact_name": "echo",
        "artefact_origin": "lab",
        "ts": "2026-10-19T12:00:00Z",
    }
    a = compute_record_hash("0" * 64, "behaviour", '{"ok":true}', **kwargs)
    b = compute_record_hash("0" * 64, "behaviour", '{"ok":true}', **kwargs)
    assert a == b
    assert len(a) == 64


def test_compute_record_hash_v2_changes_on_payload() -> None:
    kwargs = {
        "artefact_id": 1,
        "artefact_type": "mcp_tool",
        "artefact_name": "echo",
        "artefact_origin": "lab",
        "ts": "2026-10-19T12:00:00Z",
    }
    a = compute_record_hash("0" * 64, "behaviour", '{"ok":true}', **kwargs)
    b = compute_record_hash("0" * 64, "behaviour", '{"ok":false}', **kwargs)
    assert a != b


def test_compute_record_hash_v2_changes_on_ts_and_artefact() -> None:
    base = {
        "artefact_id": 1,
        "artefact_type": "mcp_tool",
        "artefact_name": "echo",
        "artefact_origin": "lab",
        "ts": "2026-10-19T12:00:00Z",
    }
    a = compute_record_hash("0" * 64, "behaviour", '{"ok":true}', **base)
    moved = {**base, "artefact_id": 2}
    renamed = {**base, "artefact_name": "not-echo"}
    redated = {**base, "ts": "1999-01-01T00:00:00Z"}
    assert a != compute_record_hash("0" * 64, "behaviour", '{"ok":true}', **moved)
    assert a != compute_record_hash("0" * 64, "behaviour", '{"ok":true}', **renamed)
    assert a != compute_record_hash("0" * 64, "behaviour", '{"ok":true}', **redated)


def test_v1_and_v2_never_collide_on_same_inputs() -> None:
    v1 = compute_record_hash_v1("0" * 64, "behaviour", '{"ok":true}')
    v2 = compute_record_hash(
        "0" * 64,
        "behaviour",
        '{"ok":true}',
        artefact_id=1,
        artefact_type="mcp_tool",
        artefact_name="echo",
        artefact_origin="lab",
        ts="2026-10-19T12:00:00Z",
    )
    assert v1 != v2
