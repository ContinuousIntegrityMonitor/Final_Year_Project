"""Shared scorer (T-16 / SYS-06, SYS-07, SYS-08)."""

from __future__ import annotations

from cim.common.scorer import (
    CAP,
    FeatureRule,
    Observation,
    ScorerConfig,
    baseline,
    score,
)

_CAT = FeatureRule(kind="categorical")
_NUM = FeatureRule(kind="numeric", threshold_milli=4000, floor_ratio=10)

_CFG = ScorerConfig(
    rules={
        "value_class": _CAT,
        "argument_shape": _CAT,
        "outcome": _CAT,
        "result_size": _NUM,
        "processes": _NUM,
        "destinations": _CAT,
    },
    window=100,
    warmup=30,
)


def _obs(
    *,
    value_class: str = "text",
    shape: str = "shape-a",
    outcome: str = "ok",
    result_size: int = 20,
    processes: int = 1,
    destinations: frozenset[str] | None = None,
) -> Observation:
    dest = destinations if destinations is not None else frozenset({"local:0"})
    return Observation(
        categorical={
            "value_class": frozenset({value_class}),
            "argument_shape": frozenset({shape}),
            "outcome": frozenset({outcome}),
            "destinations": dest,
        },
        numeric={"result_size": result_size, "processes": processes},
    )


def test_no_alert_before_warmup() -> None:
    prior = [_obs() for _ in range(29)]
    latest = _obs(value_class="private_ip")
    result = score(prior, latest, _CFG)
    assert result.warmed_up is False
    assert result.alert is False
    assert result.drifted  # scored, but gated
    assert result.drifted[0].feature == "value_class"


def test_sys08_benign_after_warmup_quiet() -> None:
    """SYS-08: many identical benign observations → no alerts after warm-up."""
    history: list[tuple[Observation, bool]] = []
    for _ in range(130):
        prior = baseline(history, _CFG)
        latest = _obs()
        result = score(prior, latest, _CFG)
        assert result.alert is False
        history.append((latest, False))


def test_sys06_never_seen_names_feature() -> None:
    """SYS-06 / SYS-07: never-seen categorical fires and names the feature."""
    prior = [_obs() for _ in range(30)]
    latest = _obs(value_class="private_ip")
    result = score(prior, latest, _CFG)
    assert result.warmed_up is True
    assert result.alert is True
    assert result.drifted[0].feature == "value_class"
    assert result.drifted[0].how == "never_seen"
    assert result.drifted[0].values == ("private_ip",)
    assert result.drifted[0].score_milli == CAP
    assert result.composite_milli == CAP


def test_a1_alerted_runs_stay_out_of_window() -> None:
    """Repeated attack alerts every time when alerted runs are excluded."""
    history: list[tuple[Observation, bool]] = [(_obs(), False) for _ in range(60)]
    alerts = 0
    for _ in range(5):
        prior = baseline(history, _CFG)
        latest = _obs(value_class="private_ip")
        result = score(prior, latest, _CFG)
        if result.alert:
            alerts += 1
        history.append((latest, result.alert))
    assert alerts == 5


def test_a1_joining_window_alerts_only_once() -> None:
    """Contrast: if alerted runs join the window, the second attack is silent."""
    history: list[tuple[Observation, bool]] = [(_obs(), False) for _ in range(60)]
    alerts = 0
    for _ in range(5):
        # Wrong rule: keep everything, including alerted.
        kept = [obs for obs, _alerted in history]
        prior = kept[-_CFG.window :]
        latest = _obs(value_class="private_ip")
        result = score(prior, latest, _CFG)
        if result.alert:
            alerts += 1
        history.append((latest, False))  # pretend it joined as normal
    assert alerts == 1


def test_zero_variance_floor_does_not_alert_on_plus_one() -> None:
    """Floor: deterministic history must not turn +1 process into an infinite z."""
    prior = [_obs(processes=1) for _ in range(30)]
    latest = _obs(processes=2)  # design table: z ≈ 1.0 → quiet at threshold 4
    result = score(prior, latest, _CFG)
    assert result.alert is False
    proc = next(d for d in _all_drifts(prior, latest) if d.feature == "processes")
    assert proc.score_milli < 4000


def test_processes_six_alerts_at_z4() -> None:
    prior = [_obs(processes=1) for _ in range(30)]
    latest = _obs(processes=6)
    result = score(prior, latest, _CFG)
    assert result.alert is True
    assert any(d.feature == "processes" and d.how == "z" for d in result.drifted)


def test_determinism() -> None:
    prior = [_obs(result_size=20 + (i % 3)) for i in range(40)]
    latest = _obs(result_size=200)
    a = score(prior, latest, _CFG)
    b = score(prior, latest, _CFG)
    assert a == b
    assert isinstance(a.composite_milli, int)
    for drift in a.drifted:
        assert isinstance(drift.score_milli, int)


def test_baseline_drops_alerted_and_caps_window() -> None:
    history = [(_obs(), False) for _ in range(10)] + [(_obs(value_class="x"), True)] * 5
    history += [(_obs(), False) for _ in range(3)]
    cfg = ScorerConfig(rules={"value_class": _CAT}, window=5, warmup=30)
    kept = baseline(history, cfg)
    assert len(kept) == 5
    assert all("x" not in obs.categorical["value_class"] for obs in kept)


def _all_drifts(prior: list[Observation], latest: Observation) -> list:
    """Score with threshold 0 so every feature drift is returned for assertions."""
    soft = ScorerConfig(
        rules={
            name: FeatureRule(kind=rule.kind, threshold_milli=0, floor_ratio=rule.floor_ratio)
            for name, rule in _CFG.rules.items()
        },
        window=_CFG.window,
        warmup=_CFG.warmup,
    )
    return list(score(prior, latest, soft).drifted)
