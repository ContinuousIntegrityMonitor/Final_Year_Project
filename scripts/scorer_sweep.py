"""T-16 threshold sweep: benign false positives and injected changes, recorded in the repo.

docs/T16_SHARED_SCORER_DESIGN.md, section 8 (acceptance: "threshold sweep recorded").

What it does, all on this machine and all with the shared scorer (`cim.common.scorer`) and
each side's own feature set (`cim.skills.alert.SKILL_SCORER`, `cim.mcp.alert.MCP_SCORER`):

1. Benign skills series: `--runs` traced runs each of word-count, csv-summary, notes-sync and
   dep-installer (`observe`, the same path `exec` uses), on a copy of the seed corpus.
2. Benign MCP series: `--mcp-calls` calls through a real `cim proxy` to the SDK test server
   (tests/mcp/sdk_server.py), split between `shout` (1 to 25 random words) and `add` (random
   operands), seeded. Observations are read back from the chained behaviour records.
3. Each series is replayed in order at z >= 2..6, as the call sites score it (warm-up 30,
   window 100, alerted runs stay out of the window), and its alerts are counted.
4. Injected changes are scored at the December threshold (z >= 4) against the full benign
   history of their series.
5. The live attacks A3 and A4 (`cim.skills.attacks`) run once each, and their real alert,
   or the lack of one, is recorded.

Needs a systemd user session and strace (skills) and the MCP SDK (MCP), as the live tests do.

usage: uv run python scripts/scorer_sweep.py [--out docs/results/T16_threshold_sweep.md]
       [--runs 140] [--mcp-calls 300] [--seed 16]
Exit status: 0 when no benign series alerts at z >= 4 and every injected row matches its
expectation, 1 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import random
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cim.common.scorer import Observation, Score, ScorerConfig, baseline, score
from cim.common.store import BaselineStore
from cim.mcp.alert import MCP_SCORER, _observations
from cim.skills.alert import SKILL_SCORER, describe, observation_of
from cim.skills.attacks import prepare, run_a3, run_a4
from cim.skills.collector import observe, tracer_available
from cim.skills.corpus import default_root, load_manifest
from cim.skills.runner import discover_skills
from cim.skills.scoped import scope_available

REPO = Path(__file__).resolve().parent.parent
SKILLS = ("word-count", "csv-summary", "notes-sync", "dep-installer")
MCP_SERVER_ID = "sweep-sdk"
THRESHOLDS = (2000, 3000, 4000, 5000, 6000)
DECEMBER = 4000
WORDS = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel", "india")


@dataclass(frozen=True)
class Series:
    name: str
    observations: list[Observation]
    config: ScorerConfig


@dataclass(frozen=True)
class Replay:
    scored: int  # observations judged after warm-up
    alerts: int


@dataclass(frozen=True)
class Injected:
    change: str
    expect_alert: bool
    result: Score


def at_threshold(config: ScorerConfig, threshold_milli: int) -> ScorerConfig:
    """The same features with every threshold set to `threshold_milli`."""
    rules = {
        name: replace(rule, threshold_milli=threshold_milli) for name, rule in config.rules.items()
    }
    return replace(config, rules=rules)


def replay(observations: Sequence[Observation], config: ScorerConfig) -> Replay:
    """Score each observation against the ones before it, as the call sites do (A1 included)."""
    history: list[tuple[Observation, bool]] = []
    scored = alerts = 0
    for latest in observations:
        result = score(baseline(history, config), latest, config)
        scored += result.warmed_up
        alerts += result.alert
        history.append((latest, result.alert))
    return Replay(scored, alerts)


def inject(
    base: Observation,
    *,
    add: Mapping[str, frozenset[str]] | None = None,
    put: Mapping[str, frozenset[str]] | None = None,
    numeric: Callable[[dict[str, int]], dict[str, int]] | None = None,
) -> Observation:
    """`base` with values added to (`add`) or replacing (`put`) features, and numbers changed."""
    categorical = dict(base.categorical)
    for name, values in (add or {}).items():
        categorical[name] = categorical.get(name, frozenset()) | values
    categorical.update(put or {})
    numbers = dict(base.numeric)
    if numeric is not None:
        numbers = numeric(numbers)
    return Observation(categorical=categorical, numeric=numbers)


def judge(series: Series, latest: Observation) -> Score:
    """Score one injected observation against the series' benign history at z >= 4."""
    config = at_threshold(series.config, DECEMBER)
    history = [(obs, False) for obs in series.observations]
    return score(baseline(history, config), latest, config)


def skills_series(runs: int, work: Path) -> list[Series]:
    root = prepare(work, default_root())
    manifest = load_manifest(root)
    skills = {skill.skill_id: skill for skill in discover_skills(root)}
    found = []
    for skill_id in SKILLS:
        skill = skills[skill_id]
        scripted = manifest[skill_id].runs
        observations = []
        for n in range(runs):
            run = scripted[n % len(scripted)]
            seen = observe(skill, skill.path / run.script, run.args)
            observations.append(observation_of(seen.payload()))
        found.append(Series(f"skill `{skill_id}`", observations, SKILL_SCORER))
    return found


async def _mcp_calls(db: Path, calls: int, seed: int) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    rng = random.Random(seed)
    env = {
        **os.environ,
        "CIM_PROXY_SERVER_ID": MCP_SERVER_ID,
        "CIM_PROXY_ORIGIN": "laptop",
        "CIM_PROXY_ROOT": "tests/mcp/sdk_server.py",
    }
    bin_dir = Path(sys.executable).parent
    params = StdioServerParameters(
        command=str(bin_dir / "cim"),
        args=[
            "proxy",
            "--db",
            str(db),
            "--",
            sys.executable,
            str(REPO / "tests/mcp/sdk_server.py"),
        ],
        env=env,
        cwd=str(REPO),
    )
    with open(os.devnull, "w", encoding="utf-8") as quiet:  # the SDK server logs every call
        async with (
            stdio_client(params, errlog=quiet) as (read, write),
            ClientSession(read, write) as session,
        ):
            await _send(session, calls, rng)


async def _send(session: Any, calls: int, rng: random.Random) -> None:
    await session.initialize()
    await session.list_tools()
    for n in range(calls):
        if n % 2 == 0:
            text = " ".join(rng.choice(WORDS) for _ in range(rng.randint(1, 25)))
            await session.call_tool("shout", {"text": text})
        else:
            await session.call_tool("add", {"a": rng.randint(0, 10**6), "b": rng.randint(0, 10**6)})


def mcp_series(calls: int, seed: int, work: Path) -> list[Series]:
    db = work / "mcp.sqlite"
    asyncio.run(_mcp_calls(db, calls, seed))
    for _ in range(50):  # the proxy's writer finishes after the client closes
        with BaselineStore(db) as store:
            found = {tool: _observations(store, MCP_SERVER_ID, tool) for tool in ("shout", "add")}
            ok = store.verify_chain().ok
        if sum(len(rows) for rows in found.values()) >= calls:
            break
        time.sleep(0.1)
    if not ok:
        raise SystemExit("scorer_sweep: the MCP replay store does not verify")
    return [
        Series(f"MCP `{tool}`", [obs for _id, obs in rows], MCP_SCORER)
        for tool, rows in found.items()
    ]


def injected_rows(series: Mapping[str, Series]) -> list[Injected]:
    notes = series["skill `notes-sync`"]
    words = series["skill `word-count`"]
    shout = series["MCP `shout`"]
    last_note, last_word, last_shout = (
        notes.observations[-1],
        words.observations[-1],
        shout.observations[-1],
    )
    largest = max(obs.numeric["result_size"] for obs in shout.observations)

    def plus(**deltas: int) -> Callable[[dict[str, int]], dict[str, int]]:
        return lambda numbers: {k: v + deltas.get(k, 0) for k, v in numbers.items()}

    def put_number(name: str, value: int) -> Callable[[dict[str, int]], dict[str, int]]:
        return lambda numbers: {**numbers, name: value}

    cases = [
        (
            notes,
            "`notes-sync` also sends to `public_ip:443` (A3-like)",
            True,
            inject(
                last_note,
                add={"destinations": frozenset({"public_ip:443"})},
                numeric=plus(destinations_n=1),
            ),
        ),
        (
            words,
            "`word-count` also runs `curl` and `sh`",
            True,
            inject(
                last_word,
                add={"binaries": frozenset({"/usr/bin/curl", "/usr/bin/sh"})},
                numeric=plus(processes=2, binaries_n=2),
            ),
        ),
        (
            words,
            "`word-count` runs 2 processes, same programs",
            False,
            inject(last_word, numeric=put_number("processes", 2)),
        ),
        (
            words,
            "`word-count` runs 6 processes, same programs",
            True,
            inject(last_word, numeric=put_number("processes", 6)),
        ),
        (
            shout,
            "MCP `shout` gets a private IP",
            True,
            inject(last_shout, put={"value_class": frozenset({"private_ip"})}),
        ),
        (
            shout,
            f"MCP `shout` result 3× the largest seen ({3 * largest} bytes)",
            True,
            inject(last_shout, numeric=put_number("result_size", 3 * largest)),
        ),
        (
            shout,
            f"MCP `shout` result 60 bytes over the largest seen ({largest + 60})",
            False,
            inject(last_shout, numeric=put_number("result_size", largest + 60)),
        ),
    ]
    return [Injected(change, expect, judge(owner, obs)) for owner, change, expect, obs in cases]


def live_attacks(work: Path) -> list[tuple[str, bool, str, bool]]:
    """(attack, expect alert, what the alert said, report passed) for A3 and A4."""
    rows = []
    for name, runner, expect in (("A3", run_a3, True), ("A4", run_a4, False)):
        root = prepare(work / name, default_root())
        with BaselineStore(work / name / "store.sqlite") as store:
            report = runner(store, root)
            if not store.verify_chain().ok:
                raise SystemExit(f"scorer_sweep: the {name} store does not verify")
        said = report.alert.detail if report.alert is not None else "no alert"
        rows.append((name, expect, said, report.passed))
    return rows


def _z(milli: int) -> str:
    return f"{milli // 1000}.{milli % 1000 // 100}"


def _features(result: Score) -> str:
    if result.drifted:
        return "; ".join(describe(result.drifted))
    return f"nothing at z ≥ 4 (composite z {_z(result.composite_milli)})"


def _commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def render(
    args: argparse.Namespace,
    benign: Sequence[Series],
    replays: Mapping[tuple[str, int], Replay],
    injected: Sequence[Injected],
    live: Sequence[tuple[str, bool, str, bool]],
) -> str:
    when = datetime.now(UTC).strftime("%Y-%m-%d")
    lines = [
        "# T-16 threshold sweep",
        "",
        "Generated by `scripts/scorer_sweep.py`; do not edit by hand. Rerun it whenever a",
        "threshold, a feature or the scorer changes",
        "([design note](../T16_SHARED_SCORER_DESIGN.md), section 8).",
        "",
        f"- Run: {when}, commit `{_commit()}`, {platform.system()} {platform.release()}, "
        f"Python {platform.python_version()}.",
        f"- Command: `uv run python scripts/scorer_sweep.py --runs {args.runs} "
        f"--mcp-calls {args.mcp_calls} --seed {args.seed}`.",
        f"- Scorer: window {SKILL_SCORER.window}, warm-up {SKILL_SCORER.warmup}, sd floor "
        "`max(1, mean / 10)`, upward only; alerted observations stay out of the window (A1).",
        "- Skills features: " + ", ".join(f"`{n}`" for n in SKILL_SCORER.rules) + ".",
        "- MCP features: " + ", ".join(f"`{n}`" for n in MCP_SCORER.rules) + ".",
        "",
        "## Benign false positives",
        "",
        "Alerts over the observations scored after warm-up, with every threshold set to the"
        " column's z. A never-seen value scores z 10 whatever the threshold.",
        "",
        "| Series | Observations | Scored | "
        + " | ".join(f"z≥{t // 1000}" for t in THRESHOLDS)
        + " |",
        "|---|---|---|" + "---|" * len(THRESHOLDS),
    ]
    for item in benign:
        cells = [str(replays[(item.name, t)].alerts) for t in THRESHOLDS]
        scored = replays[(item.name, THRESHOLDS[0])].scored
        lines.append(
            f"| {item.name} | {len(item.observations)} | {scored} | " + " | ".join(cells) + " |"
        )
    total = sum(replays[(item.name, THRESHOLDS[0])].scored for item in benign)
    lines += [
        "",
        f"{total} benign observations scored in all.",
        "",
        "## Injected changes, at z ≥ 4",
        "",
        "Each change is applied to the last benign observation of its series and scored against"
        " that series' whole benign history.",
        "",
        "| Change | Expected | Result | Top features |",
        "|---|---|---|---|",
    ]
    for row in injected:
        expected = "alert" if row.expect_alert else "quiet"
        got = "alert" if row.result.alert else "quiet"
        mark = "" if got == expected else " **(unexpected)**"
        lines.append(f"| {row.change} | {expected} | {got}{mark} | {_features(row.result)} |")
    lines += [
        "",
        "## Live attacks (T-17), through `record_behaviour`",
        "",
        "The local listener's port is random, so A3's destination port changes from run to run.",
        "",
        "| Attack | Expected | Alert written | Attack check |",
        "|---|---|---|---|",
    ]
    for name, expect, said, passed in live:
        wanted = "alert" if expect else "no alert"
        lines.append(f"| {name} | {wanted} | {said} | {'PASS' if passed else 'FAIL'} |")
    margin = [
        f"{item.name} {replays[(item.name, t)].alerts} at z ≥ {t // 1000}"
        for t in THRESHOLDS
        if t < DECEMBER
        for item in benign
        if replays[(item.name, t)].alerts
    ]
    lines += [
        "",
        "## Reading it",
        "",
        "- Below the December threshold, benign alerts: "
        + ("; ".join(margin) if margin else "none")
        + ". That is the margin z ≥ 4 leaves over this machine's benign spread.",
        "- The seed skills are deterministic (every run of a helper does the same thing), so their"
        " benign series have almost no spread; the sd floor is what keeps small moves quiet.",
        "  A benign zero here shows the gate works. It does not show z ≥ 4 is right for real"
        " skills, which vary more: calibration on a realistic benign set is T-22 / T-28 (January).",
        "- The MCP series vary (1 to 25 words per `shout`, random `add` operands), so the z path is"
        " exercised on real spread.",
        "- Never-seen alerts do not depend on the threshold. The December threshold stays z ≥ 4 for"
        " every numeric feature.",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "docs/results/T16_threshold_sweep.md")
    parser.add_argument("--runs", type=int, default=140, help="traced runs per skill")
    parser.add_argument("--mcp-calls", type=int, default=300, help="benign MCP calls in all")
    parser.add_argument("--seed", type=int, default=16)
    args = parser.parse_args(argv)
    if not scope_available() or not tracer_available():
        raise SystemExit("scorer_sweep: needs a systemd user session and strace (as `observe`)")

    with tempfile.TemporaryDirectory(prefix="cim-sweep-") as tmp:
        work = Path(tmp)
        print(f"scorer_sweep: {args.runs} traced runs each of {', '.join(SKILLS)}", flush=True)
        benign = skills_series(args.runs, work / "skills")
        print(f"scorer_sweep: {args.mcp_calls} MCP calls through cim proxy", flush=True)
        benign += mcp_series(args.mcp_calls, args.seed, work)
        print("scorer_sweep: live A3 and A4", flush=True)
        live = live_attacks(work / "attacks")

    replays = {
        (item.name, t): replay(item.observations, at_threshold(item.config, t))
        for item in benign
        for t in THRESHOLDS
    }
    injected = injected_rows({item.name: item for item in benign})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(args, benign, replays, injected, live), encoding="utf-8")
    print(f"scorer_sweep: wrote {args.out}")

    false_positives = sum(replays[(item.name, DECEMBER)].alerts for item in benign)
    mismatched = [row.change for row in injected if row.result.alert != row.expect_alert]
    failed = [name for name, _e, _s, passed in live if not passed]
    if false_positives or mismatched or failed:
        print(
            f"scorer_sweep: FAIL ({false_positives} benign alerts at z>=4; "
            f"unexpected: {mismatched or 'none'}; attacks failed: {failed or 'none'})"
        )
        return 1
    print("scorer_sweep: PASS (0 benign alerts at z>=4; every injected row as expected)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
