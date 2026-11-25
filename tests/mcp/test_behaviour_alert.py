"""Behaviour alert after warm-up (T-16, MCP half).

Scoring reads chained behaviour records (contract 1.1), not envelope_obs.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, cast

from cim.common.schema.mcp import McpBehaviourPayload, ValueClass
from cim.common.store import BaselineStore
from cim.mcp.alert import score_latest
from cim.mcp.envelope import WARMUP, argument_shape, record_observation, value_classes
from cim.mcp.events import append_mcp
from cim.mcp.inventory import sha256_canonical

TS = "2026-11-11T12:00:00Z"
_DIGEST = "a" * 64


def _append_behaviour(
    store: BaselineStore,
    *,
    tool_aid: int,
    n: int,
    arguments: dict[str, Any],
    result_size: int = 20,
    outcome: str = "ok",
) -> int:
    classes = cast(list[ValueClass], value_classes(arguments))
    payload = McpBehaviourPayload(
        server_id="demo",
        tool_id="send_email",
        invocation_id=f"test:{n}",
        request_digest=_DIGEST,
        binaries_executed=[],
        file_write_targets=[],
        egress=[],
        process_count=0,
        duration_us=1,
        outcome=cast(Any, outcome),
        response_bytes=result_size,
        session_id="test",
        seq=n,
        argument_shape_digest=sha256_canonical(argument_shape(arguments)),
        value_classes=classes,
    )
    return append_mcp(
        store,
        tool_aid,
        artefact_type="mcp_tool",
        server_id="demo",
        tool_id="send_email",
        kind="behaviour",
        payload=payload,
        ts=TS,
    )


def _fill(
    store: BaselineStore, server_aid: int, tool_aid: int, count: int, arguments: dict[str, str]
) -> None:
    for i in range(1, count + 1):
        rid = _append_behaviour(store, tool_aid=tool_aid, n=i, arguments=arguments)
        score_latest(
            store,
            artefact_id=server_aid,
            server_id="demo",
            tool="send_email",
            ts=TS,
            observation_record_id=rid,
        )


def test_warmup_does_not_alert(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    with BaselineStore(db) as store:
        server_aid = store.append_artefact("mcp_server", "demo", "dashboard")
        tool_aid = store.append_artefact("mcp_tool", "send_email", "dashboard")
        _fill(store, server_aid, tool_aid, WARMUP, {"body": "hello"})
        alerts = [row for row in store.read_records() if row.kind == "alert"]
    assert alerts == []


def test_new_value_class_alerts_once_warm(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    with BaselineStore(db) as store:
        server_aid = store.append_artefact("mcp_server", "demo", "dashboard")
        tool_aid = store.append_artefact("mcp_tool", "send_email", "dashboard")
        _fill(store, server_aid, tool_aid, WARMUP, {"body": "hello"})
        rid = _append_behaviour(
            store,
            tool_aid=tool_aid,
            n=WARMUP + 1,
            arguments={"body": "10.1.1.1"},
        )
        reasons = score_latest(
            store,
            artefact_id=server_aid,
            server_id="demo",
            tool="send_email",
            ts=TS,
            observation_record_id=rid,
        )
        alerts = [row for row in store.read_records() if row.kind == "alert"]
        assert store.verify_chain().ok
    assert reasons == ["value class private_ip"]
    assert len(alerts) == 1
    assert "private_ip" in alerts[0].payload
    assert "Input now includes private_ip" in alerts[0].payload


def test_wiping_envelope_obs_does_not_silence_alert(tmp_path: Path) -> None:
    """M1: off-chain envelope_obs must not be required for scoring."""
    db = tmp_path / "store.sqlite"
    with BaselineStore(db) as store:
        server_aid = store.append_artefact("mcp_server", "demo", "dashboard")
        tool_aid = store.append_artefact("mcp_tool", "send_email", "dashboard")
        _fill(store, server_aid, tool_aid, WARMUP, {"body": "hello"})
        for _ in range(5):
            record_observation(
                store.path,
                server_id="demo",
                tool="send_email",
                arguments={"body": "hello"},
                result_size=20,
                outcome="ok",
            )
        with sqlite3.connect(store.path) as conn:
            conn.execute("DELETE FROM envelope_obs")
            conn.commit()
        rid = _append_behaviour(
            store,
            tool_aid=tool_aid,
            n=WARMUP + 1,
            arguments={"body": "10.1.1.1"},
        )
        reasons = score_latest(
            store,
            artefact_id=server_aid,
            server_id="demo",
            tool="send_email",
            ts=TS,
            observation_record_id=rid,
        )
        assert store.verify_chain().ok
    assert reasons == ["value class private_ip"]


def test_envelope_obs_alone_does_not_alert(tmp_path: Path) -> None:
    """Scoring must ignore envelope_obs even when it looks unusual."""
    db = tmp_path / "store.sqlite"
    with BaselineStore(db) as store:
        server_aid = store.append_artefact("mcp_server", "demo", "dashboard")
        tool_aid = store.append_artefact("mcp_tool", "send_email", "dashboard")
        # Need at least one real behaviour row id to call the API; scoring that
        # warm-up-shaped row with only envelope_obs unusual must not alert.
        rid = _append_behaviour(store, tool_aid=tool_aid, n=1, arguments={"body": "hello"})
        for _ in range(WARMUP):
            record_observation(
                store.path,
                server_id="demo",
                tool="send_email",
                arguments={"body": "hello"},
                result_size=20,
                outcome="ok",
            )
        record_observation(
            store.path,
            server_id="demo",
            tool="send_email",
            arguments={"body": "10.1.1.1"},
            result_size=20,
            outcome="ok",
        )
        reasons = score_latest(
            store,
            artefact_id=server_aid,
            server_id="demo",
            tool="send_email",
            ts=TS,
            observation_record_id=rid,
        )
    assert reasons == []


def test_a1_repeated_attack_alerts_every_time(tmp_path: Path) -> None:
    """Alerted calls stay out of the window, so the same attack fires again."""
    db = tmp_path / "store.sqlite"
    with BaselineStore(db) as store:
        server_aid = store.append_artefact("mcp_server", "demo", "dashboard")
        tool_aid = store.append_artefact("mcp_tool", "send_email", "dashboard")
        _fill(store, server_aid, tool_aid, WARMUP, {"body": "hello"})
        alerts = 0
        for i in range(1, 4):
            rid = _append_behaviour(
                store,
                tool_aid=tool_aid,
                n=WARMUP + i,
                arguments={"body": "10.1.1.1"},
            )
            reasons = score_latest(
                store,
                artefact_id=server_aid,
                server_id="demo",
                tool="send_email",
                ts=TS,
                observation_record_id=rid,
            )
            if reasons:
                alerts += 1
        assert store.verify_chain().ok
    assert alerts == 3


def test_finding1_scores_named_record_not_newest(tmp_path: Path) -> None:
    """Finding 1: scoring an older attack id still alerts after a newer benign append."""
    db = tmp_path / "store.sqlite"
    with BaselineStore(db) as store:
        server_aid = store.append_artefact("mcp_server", "demo", "dashboard")
        tool_aid = store.append_artefact("mcp_tool", "send_email", "dashboard")
        _fill(store, server_aid, tool_aid, WARMUP, {"body": "hello"})
        attack_id = _append_behaviour(
            store,
            tool_aid=tool_aid,
            n=WARMUP + 1,
            arguments={"body": "10.1.1.1"},
        )
        benign_id = _append_behaviour(
            store,
            tool_aid=tool_aid,
            n=WARMUP + 2,
            arguments={"body": "hello"},
        )
        # Wrong order if we always scored "newest": scoring twice without ids
        # would miss the attack. With ids, each row is judged correctly.
        attack_reasons = score_latest(
            store,
            artefact_id=server_aid,
            server_id="demo",
            tool="send_email",
            ts=TS,
            observation_record_id=attack_id,
        )
        benign_reasons = score_latest(
            store,
            artefact_id=server_aid,
            server_id="demo",
            tool="send_email",
            ts=TS,
            observation_record_id=benign_id,
        )
        alerts = [
            json.loads(row.payload)["observation_record_id"]
            for row in store.read_records()
            if row.kind == "alert"
        ]
        assert store.verify_chain().ok
    assert attack_reasons == ["value class private_ip"]
    assert benign_reasons == []
    assert alerts == [attack_id]


def test_finding1_scoring_newest_first_does_not_double_alert(tmp_path: Path) -> None:
    """Scoring the benign newest first must not also attach an alert to that id for the attack."""
    db = tmp_path / "store.sqlite"
    with BaselineStore(db) as store:
        server_aid = store.append_artefact("mcp_server", "demo", "dashboard")
        tool_aid = store.append_artefact("mcp_tool", "send_email", "dashboard")
        _fill(store, server_aid, tool_aid, WARMUP, {"body": "hello"})
        attack_id = _append_behaviour(
            store,
            tool_aid=tool_aid,
            n=WARMUP + 1,
            arguments={"body": "10.1.1.1"},
        )
        public_id = _append_behaviour(
            store,
            tool_aid=tool_aid,
            n=WARMUP + 2,
            arguments={"body": "8.8.8.8"},
        )
        first = score_latest(
            store,
            artefact_id=server_aid,
            server_id="demo",
            tool="send_email",
            ts=TS,
            observation_record_id=public_id,
        )
        second = score_latest(
            store,
            artefact_id=server_aid,
            server_id="demo",
            tool="send_email",
            ts=TS,
            observation_record_id=attack_id,
        )
        alert_ids = [
            json.loads(row.payload)["observation_record_id"]
            for row in store.read_records()
            if row.kind == "alert"
        ]
    assert "private_ip" in " ".join(first) or "public_ip" in " ".join(first)
    assert second == ["value class private_ip"]
    assert alert_ids == [public_id, attack_id]


def test_finding2_outcome_only_joins_window(tmp_path: Path) -> None:
    """Finding 2: after the first error alerts, a second identical error stays quiet."""
    db = tmp_path / "store.sqlite"
    with BaselineStore(db) as store:
        server_aid = store.append_artefact("mcp_server", "demo", "dashboard")
        tool_aid = store.append_artefact("mcp_tool", "send_email", "dashboard")
        _fill(store, server_aid, tool_aid, WARMUP, {"body": "hello"})
        first_id = _append_behaviour(
            store,
            tool_aid=tool_aid,
            n=WARMUP + 1,
            arguments={"body": "hello"},
            outcome="error",
        )
        first = score_latest(
            store,
            artefact_id=server_aid,
            server_id="demo",
            tool="send_email",
            ts=TS,
            observation_record_id=first_id,
        )
        second_id = _append_behaviour(
            store,
            tool_aid=tool_aid,
            n=WARMUP + 2,
            arguments={"body": "hello"},
            outcome="error",
        )
        second = score_latest(
            store,
            artefact_id=server_aid,
            server_id="demo",
            tool="send_email",
            ts=TS,
            observation_record_id=second_id,
        )
        assert store.verify_chain().ok
    assert first == ["outcome error"]
    assert second == []
