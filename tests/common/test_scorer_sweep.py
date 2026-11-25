"""The pure parts of scripts/scorer_sweep.py (T-16 threshold sweep)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from cim.common.scorer import Observation
from cim.skills.alert import SKILL_SCORER

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "scorer_sweep.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("scorer_sweep", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sweep = _load()


def _obs(processes: int = 1, destinations: frozenset[str] = frozenset()) -> Observation:
    return Observation(
        categorical={"binaries": frozenset({"/usr/bin/python3"}), "destinations": destinations},
        numeric={"processes": processes, "binaries_n": 1, "destinations_n": len(destinations)},
    )


def test_at_threshold_sets_every_rule() -> None:
    config = sweep.at_threshold(SKILL_SCORER, 2000)
    assert {rule.threshold_milli for rule in config.rules.values()} == {2000}
    assert {name: rule.kind for name, rule in config.rules.items()} == {
        name: rule.kind for name, rule in SKILL_SCORER.rules.items()
    }
    assert SKILL_SCORER.rules["processes"].threshold_milli == 4000  # the original is untouched


def test_replay_counts_scored_and_alerts_with_a1() -> None:
    series = [_obs() for _ in range(40)] + [_obs(destinations=frozenset({"public_ip:443"}))] * 3
    result = sweep.replay(series, SKILL_SCORER)
    assert result.scored == 13  # 40 + 3 observations, the first 30 are warm-up
    assert result.alerts == 3  # alerted runs stay out of the window, so all three alert


def test_lower_threshold_catches_smaller_moves() -> None:
    series = [_obs() for _ in range(30)] + [_obs(processes=4)]  # z 3.0 under the floor
    assert sweep.replay(series, sweep.at_threshold(SKILL_SCORER, 3000)).alerts == 1
    assert sweep.replay(series, sweep.at_threshold(SKILL_SCORER, 4000)).alerts == 0


def test_inject_adds_and_replaces() -> None:
    base = _obs(destinations=frozenset({"private_ip:9"}))
    added = sweep.inject(
        base,
        add={"destinations": frozenset({"public_ip:443"})},
        numeric=lambda n: {**n, "processes": 6},
    )
    assert added.categorical["destinations"] == frozenset({"private_ip:9", "public_ip:443"})
    assert added.numeric["processes"] == 6
    put = sweep.inject(base, put={"destinations": frozenset({"domain:443"})})
    assert put.categorical["destinations"] == frozenset({"domain:443"})
    assert base.numeric["processes"] == 1  # the base observation is unchanged
