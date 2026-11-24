"""Shared behaviour scorer (T-16). Pure: no store, no I/O, no clock, no floats.

Both MCP and skills turn their own chained records into ``Observation`` values and
call ``score``. Integer milli-z scores only (docs/T16_SHARED_SCORER_DESIGN.md).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isqrt
from typing import Literal

CAP = 10_000  # never-seen and z-cap (z = 10.0)
SCORER_VERSION = 1


@dataclass(frozen=True)
class Observation:
    """One scorable run or call."""

    categorical: Mapping[str, frozenset[str]]  # feature -> values in this run
    numeric: Mapping[str, int]  # feature -> integer count or size


@dataclass(frozen=True)
class FeatureRule:
    """How one named feature is judged."""

    kind: Literal["categorical", "numeric"]
    threshold_milli: int = 4000  # z >= 4.0 by default; never-seen always scores CAP
    floor_ratio: int = 10  # numeric: sd floor = max(1, mean / floor_ratio)


@dataclass(frozen=True)
class ScorerConfig:
    """Window, warm-up, and the feature rules the caller cares about."""

    rules: Mapping[str, FeatureRule]  # feature without a rule is ignored
    window: int = 100
    warmup: int = 30


@dataclass(frozen=True)
class Drift:
    """One feature that crossed its threshold on the latest observation."""

    feature: str
    how: Literal["never_seen", "z"]
    values: tuple[str, ...]  # never_seen: new values; z: (str(latest),)
    score_milli: int
    threshold_milli: int


@dataclass(frozen=True)
class Score:
    """Result of scoring one latest observation against a prior window."""

    warmed_up: bool
    composite_milli: int  # max score_milli over all features (0 if none)
    drifted: tuple[Drift, ...]  # at or over threshold, highest first, top 3
    alert: bool  # warmed_up and drifted is not empty


def baseline(
    history: Sequence[tuple[Observation, bool]], config: ScorerConfig
) -> list[Observation]:
    """Last ``window`` observations that did not alert (A1 / design section 5)."""
    kept = [obs for obs, alerted in history if not alerted]
    if config.window <= 0:
        return []
    return list(kept[-config.window :])


def score(prior: Sequence[Observation], latest: Observation, config: ScorerConfig) -> Score:
    """Compare ``latest`` to ``prior``. Does not mutate anything."""
    warmed_up = len(prior) >= config.warmup
    candidates: list[Drift] = []
    for feature, rule in config.rules.items():
        if rule.kind == "categorical":
            drift = _categorical(feature, rule, prior, latest)
        else:
            drift = _numeric(feature, rule, prior, latest)
        if drift is not None and drift.score_milli >= rule.threshold_milli:
            candidates.append(drift)
    candidates.sort(key=lambda item: (-item.score_milli, item.feature))
    drifted = tuple(candidates[:3])
    composite = max((item.score_milli for item in drifted), default=0)
    # Also consider features that scored but did not meet threshold for composite?
    # Design: composite = max over features. Use all scored features for composite.
    all_scores = _all_feature_scores(prior, latest, config)
    if all_scores:
        composite = max(all_scores)
    return Score(
        warmed_up=warmed_up,
        composite_milli=composite,
        drifted=drifted,
        alert=warmed_up and bool(drifted),
    )


def _all_feature_scores(
    prior: Sequence[Observation], latest: Observation, config: ScorerConfig
) -> list[int]:
    scores: list[int] = []
    for feature, rule in config.rules.items():
        if rule.kind == "categorical":
            drift = _categorical(feature, rule, prior, latest)
        else:
            drift = _numeric(feature, rule, prior, latest)
        if drift is not None:
            scores.append(drift.score_milli)
    return scores


def _categorical(
    feature: str,
    rule: FeatureRule,
    prior: Sequence[Observation],
    latest: Observation,
) -> Drift | None:
    latest_values = latest.categorical.get(feature, frozenset())
    if not latest_values:
        return None
    seen: set[str] = set()
    for obs in prior:
        seen.update(obs.categorical.get(feature, frozenset()))
    fresh = tuple(sorted(latest_values - seen))
    if not fresh:
        return None
    return Drift(
        feature=feature,
        how="never_seen",
        values=fresh,
        score_milli=CAP,
        threshold_milli=rule.threshold_milli,
    )


def _numeric(
    feature: str,
    rule: FeatureRule,
    prior: Sequence[Observation],
    latest: Observation,
) -> Drift | None:
    if feature not in latest.numeric:
        return None
    if not prior:
        return None
    values = [obs.numeric[feature] for obs in prior if feature in obs.numeric]
    if not values:
        return None
    n = len(values)
    total = sum(values)
    total_squares = sum(v * v for v in values)
    x = latest.numeric[feature]
    above = n * x - total
    if above <= 0:
        return Drift(
            feature=feature,
            how="z",
            values=(str(x),),
            score_milli=0,
            threshold_milli=rule.threshold_milli,
        )
    r = rule.floor_ratio if rule.floor_ratio > 0 else 10
    variance_term = n * total_squares - total * total
    floor_n2 = n * n
    floor_mean = (total * total) // (r * r) if r else 0
    spread = max(variance_term, floor_n2, floor_mean)
    if spread <= 0:
        spread = 1
    score_milli = min(CAP, isqrt((above * above * 1_000_000) // spread))
    return Drift(
        feature=feature,
        how="z",
        values=(str(x),),
        score_milli=score_milli,
        threshold_milli=rule.threshold_milli,
    )
