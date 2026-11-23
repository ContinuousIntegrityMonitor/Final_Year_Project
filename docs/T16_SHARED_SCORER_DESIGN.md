# T-16 shared scorer: design note

From Fasih, for Hamza (T-16 lead). Ask A2 in [`docs/FASIH_ASK_2026-11-19.md`](FASIH_ASK_2026-11-19.md). **A proposal: no code is written until you agree it.** Your answers to section 11 decide the implementation PRs.

## 1. Why

The plan (section 4.10, T-16) asks for one library both sides call:

- a rolling z-score for numeric features;
- a never-seen-value flag for categorical features;
- composite score = the largest deviation;
- a configurable threshold, with per-feature thresholds (risk R4);
- warm-up gating;
- alerts that name the top 3 drifted features.

The acceptance tests are SYS-06, SYS-07 and SYS-08:
- 100+ benign runs after warm-up give zero alerts;
- an injected never-seen class fires an alert naming that feature;
- the threshold sweep is recorded in the repo.

What exists today:

| Side | What it has | What is missing |
|---|---|---|
| MCP | `cim/mcp/alert.py` `score_latest`: fixed rules (new value class, new argument shape, first error, result at least 3× the median and +50 bytes) | No z-score, no threshold, nothing skills can call (review A2). An unusual call joins the baseline, so a repeated attack alerts once (A1). It reads `envelope_obs`, which is outside the chain (test report M1). |
| Skills | `cim/skills/envelope.py` profiles: support sets and integer sums (count, sum, sum of squares), derived from chained records | Nothing scores a new run, so no skill alert exists. The board's skills section (U1) has an empty `alerts` list waiting. |

## 2. Shape of the library

`src/cim/common/scorer.py`, at the border: both review it, as section 4.2 of the plan requires. It is pure: no store, no I/O, no clock. Each side converts its own records into observations and decides where the alert goes.

```python
@dataclass(frozen=True)
class Observation:
    categorical: Mapping[str, frozenset[str]]  # feature -> values seen in this run
    numeric: Mapping[str, int]                  # feature -> integer count or size

@dataclass(frozen=True)
class FeatureRule:
    kind: Literal["categorical", "numeric"]
    threshold_milli: int = 4000      # z >= 4.0 by default; never-seen always scores CAP
    floor_ratio: int = 10            # numeric: sd floor = max(1, mean / floor_ratio)

@dataclass(frozen=True)
class ScorerConfig:
    window: int = 100
    warmup: int = 30
    rules: Mapping[str, FeatureRule]  # one per feature; a feature without a rule is ignored

@dataclass(frozen=True)
class Drift:
    feature: str
    how: Literal["never_seen", "z"]
    values: tuple[str, ...]          # never_seen: the new values; z: (str(latest),)
    score_milli: int                 # CAP for never_seen, else |z| * 1000, capped at CAP
    threshold_milli: int

@dataclass(frozen=True)
class Score:
    warmed_up: bool
    composite_milli: int             # max score_milli over all features
    drifted: tuple[Drift, ...]       # features at or over their threshold, highest first, top 3
    alert: bool                      # warmed_up and drifted is not empty

def baseline(history: Sequence[tuple[Observation, bool]], config: ScorerConfig) -> list[Observation]:
    """The last `window` observations that did not alert (section 5)."""

def score(prior: Sequence[Observation], latest: Observation, config: ScorerConfig) -> Score:
    ...
```

`SkillProfile` already holds the skills side of this. For MCP, an adapter turns each call into an `Observation`.

## 3. The maths, in integers

Stored payloads cannot hold floats (`canonical_json` refuses them), and the result must be identical on every machine. So every score is an integer in thousandths of a standard deviation ("milli-z").

**Categorical feature.** Any value of the latest run that is not in the union of the window's values scores `CAP` = 10 000 (z = 10). A run can bring several new values; all are named.

**Numeric feature, upward only.** The window holds n values with sum S and sum of squares Q, which is exactly the `Numeric` triple in the skills profile. For the latest value x:

```
above  = n·x − S                                 (n times the distance above the mean)
spread = max(n·Q − S²,  n²,  S² // r²)           (n² × variance, floored; r = floor_ratio)
score  = 0                           if above ≤ 0
       = min(CAP, isqrt(above² · 10⁶ // spread))  otherwise
```

- `above / sqrt(n·Q − S²)` is the usual z-score, (x − mean)/sd, rewritten so that it needs no division until the last integer square root.
- **The floor** keeps the standard deviation at least `max(1, mean / r)`. The seed corpus is deterministic (every run of `word-count` starts exactly one process), so its standard deviation is 0, and without a floor one extra process would be an infinite z. With r = 10: `word-count` needs 6 processes instead of 1 to reach z = 5. For an MCP result of about 284 bytes whose size barely varies, the floor is about 28 bytes, so z = 4 needs about 114 bytes above the mean; a result that varies more is judged on its real spread.
- **Upward only:** fewer processes, fewer writes or a smaller result is not what an attack looks like, and two-sided scoring doubles the false positives. A rule can be made two-sided later if a feature needs it.

**Composite and alert.** Composite = max over features, as the plan says. A feature has *drifted* when its score reaches its own threshold. The alert carries the top 3 drifted features by score. There is no alert before warm-up (fewer than 30 observations in the window).

## 4. Features per side

| Side | Categorical | Numeric (upward) |
|---|---|---|
| Skills | `binaries`, `write_targets`, `destinations` (`dest_class:port`) | `processes`, `binaries_n`, `writes_n`, `destinations_n` |
| MCP | `argument_shape`, `value_class`, `outcome` | `result_size` |

How today's MCP rules map:
- new value class, new argument shape, first error → `value_class`, `argument_shape`, `outcome` never seen (same behaviour);
- 3× median and +50 → `result_size` z-score.

On the live T-16 store from the test report, the prototype gives the same single alert as `score_latest`: the 36th `shout` call, `value_class never seen: private_ip`.

Left out of v1:
- **`duration_us`:** wall clock, different on every run; the skills profile already leaves it out of the reproducible part.
- **MCP call rate and error rate:** per-window rates, not per-call values; the plan lists them for T-14, and they can join as numeric features later without changing the interface.

## 5. What joins the baseline (fixes A1)

Today an alerted call joins the window, so the second identical attack call is "normal": one alert, then silence.

**Proposal:** an observation that raised an alert stays out of the window. Each side already knows which runs alerted, because the alert record names the run (section 7). The prototype, one A3-style attack repeated 5 times after 60 benign runs:

| Rule | Alerts |
|---|---|
| Alerted runs join the window (today's MCP behaviour) | 1 |
| Alerted runs stay out (proposal) | 5 |

The cost: a legitimate change in behaviour keeps alerting until someone re-baselines, and re-baselining is FYP II (T-31, provenance re-baseline). For December that is the honest behaviour: the demo's A3 must "fire reliably" (T-17), and A4 (legitimate update) is a file change with unchanged behaviour, so it never reaches this rule. The board can group repeats of one feature and value (decision 3).

## 6. Inputs come from the chain (fixes M1)

- **Skills:** already. Observations are built from the hash-chained `behaviour` records, and nothing beside the chain is read.
- **MCP:** today the scorer reads `envelope_obs`; one `UPDATE` there silences an alert while `verify-chain` passes (test report M1). Proposal for contract v1.1: `McpBehaviourPayload` gains `response_bytes` (already drafted on `t02-contract-fixes`), `argument_shape_digest` (sha256 of the canonical shape) and `value_classes` (sorted list). All three are optional, so v1.0 records still validate. The MCP adapter then builds observations from chained records. `envelope_obs` can stay as a cache for `cim envelope`, but nothing scores from it.

Until v1.1 lands, the MCP adapter can keep reading `envelope_obs`. That is a known limit to state in the threat model, not a reason to wait.

## 7. Where each side calls it, and the alert record

| Side | Call site | Alert record |
|---|---|---|
| MCP | `StoreSink.apply`, right after the behaviour record, where `score_latest` is called today | kind `alert` under the server artefact, as today |
| Skills | `record_behaviour`, right after the behaviour record | kind `alert` under the skill's artefact |

Proposed shared alert payload (`BehaviourAlertPayload` in v1.1, keeping `code` and `reason` as every alert's common fields, as in the drafted contract answers):

```json
{
  "code": "skill_behaviour_drift",
  "reason": "behaviour_drift",
  "skill_id": "notes-sync",
  "observation_record_id": 812,
  "composite_milli": 10000,
  "features": [
    {"feature": "destinations", "how": "never_seen", "values": ["public_ip:443"],
     "score_milli": 10000, "threshold_milli": 4000}
  ],
  "window": 100,
  "scorer_version": 1,
  "detail": "notes-sync changed how it behaves: destinations never seen: public_ip:443"
}
```

- MCP uses `code: "mcp_behaviour_drift"`, `server_id` and `tool_id` in place of `skill_id`, and keeps `input_change` / `output_change` for the page.
- `observation_record_id` comes from `append_record`'s return value. It links the alert to the exact run it judged; section 5 uses it to keep that run out of the window; and the evidence drawer (FYP II) can follow it.
- **A scorer fault must leave a record** (test report M4). The proxy records `proxy_capture_failed` with `stage: "score"`, and the skills side records `skill_score_failed`. The run itself is already stored either way.

## 8. Thresholds: the sweep

The prototype is the maths above, run over real stores from this laptop:
- 140 traced runs each of `word-count`, `csv-summary`, `notes-sync`, `dep-installer`;
- a 300-call benign MCP replay through `cim proxy` with varied inputs (1 to 25 words per `shout`, random `add` operands).

**Benign false positives** (alerts over the observations scored after warm-up):

| Series | Scored | z≥2 | z≥3 | z≥4 | z≥5 | z≥6 |
|---|---|---|---|---|---|---|
| skill `word-count` | 110 | 0 | 0 | 0 | 0 | 0 |
| skill `notes-sync` | 110 | 0 | 0 | 0 | 0 | 0 |
| skill `dep-installer` | 110 | 0 | 0 | 0 | 0 | 0 |
| skill `csv-summary` | 110 | 0 | 0 | 0 | 0 | 0 |
| MCP `shout` | 120 | 0 | 0 | 0 | 0 | 0 |
| MCP `add` | 120 | 0 | 0 | 0 | 0 | 0 |

**Injected changes** against the same history, at z ≥ 4:

| Change | Result | Top features |
|---|---|---|
| `notes-sync` also sends to `public_ip:443` (A3-like) | alert | `destinations` never seen: `public_ip:443` |
| `word-count` also runs `curl` and `sh` | alert | `binaries` never seen; `processes` z 2.0; `binaries_n` z 2.0 |
| `word-count` runs 2 processes, same programs | quiet | `processes` z 1.0 |
| `word-count` runs 6 processes, same programs | alert | `processes` z 5.0 |
| MCP `shout` gets a private IP | alert | `value_class` never seen: `private_ip` |
| MCP `shout` result 3× the largest seen (1353 bytes) | alert | `result_size` z 10.0 |
| MCP `shout` result 60 bytes over the largest seen (511) | quiet | `result_size` z 2.9 |

**Reading it honestly.** The benign zero holds at every threshold because the seed corpus is deterministic and the floor absorbs small variation. That shows the gate works. It does not show that z = 4 is right for real skills, which vary more. Calibration on a realistic benign set is T-22 / T-28 (January). For December I propose z ≥ 4 for every numeric feature. Never-seen alerts are independent of the threshold.

The implementation PR commits the sweep as a script (`scripts/scorer_sweep.py`) and its output (`docs/results/T16_threshold_sweep.md`), which is the "threshold sweep recorded in the repo" acceptance item. Rerun it whenever a threshold changes.

## 9. Tests (one per acceptance item)

- **SYS-08:** 130 benign observations per side (synthetic in unit tests, real ones in the sweep) → zero alerts after warm-up.
- **SYS-06 / SYS-07:** a never-seen value fires an alert naming that feature, on both sides, while the artefact's file and schema hashes are unchanged.
- No alert before 30 observations; the 31st can alert.
- Determinism: the same inputs give an identical `Score` on every run, and nothing in it is a float.
- The A1 rule: a repeated attack alerts every time.
- The floor: a zero-variance history does not turn +1 into an alert.
- MCP parity: both tests in `tests/mcp/test_behaviour_alert.py` (warm-up stays quiet; a new value class alerts once warm) still pass, plus new ones for argument shape, first error and result size.

## 10. Work split and order

1. **This note agreed** (you, then Fasih).
2. **PR: `common/scorer.py` and its tests.** Fasih writes it; both review (border).
3. **PR: skills call site.** `record_behaviour` scores and writes `skill_behaviour_drift`; the board's skills `alerts` fill in with no board change. Fasih.
4. **PR: MCP switch.** `score_latest` keeps its signature and calls the library; the A1 rule. Yours, or Fasih's if you pre-agree.
5. **Contract v1.1 fields** for section 6 and the alert payload. Joint; it goes in the v1.1 PR (ask A4).
6. **Sweep script and recorded output.** Fasih, with PR 2 or 3.

Items 2, 3 and 6 are enough for the skills half of the December demo (C4 on skills, T-17 A3).

## 11. Decisions for you

1. Library location and interface (sections 2 and 3), including integer milli-z and the sd floor `max(1, mean/10)`.
2. Alerted runs stay out of the window (section 5): agree, or keep today's rule.
3. Repeated alerts: one record per alerting run (proposal, simplest evidence), with the board grouping them; or one alert per feature and value until re-baseline.
4. Contract v1.1: the three MCP behaviour fields (section 6) and `BehaviourAlertPayload` (section 7).
5. Default threshold z ≥ 4 for numeric features in December (section 8).
6. Who does item 4 of section 10, the MCP switch.

## 12. Known limits (for the threat model, T-03)

- **Warm-up learns anything:** a value that appears in the first 30 runs is never flagged later (test report L7).
- **Slow drift:** a value that rises a little each run moves the mean with it ("boiling frog"). That is the T-33 attack; v1 does not defend against it. A second, frozen reference window is the usual answer.
- **Mimicry:** an attack that only uses programs, paths and destinations already in the window is invisible to the categorical features.
- **MCP inputs outside the chain** until v1.1 (section 6).
