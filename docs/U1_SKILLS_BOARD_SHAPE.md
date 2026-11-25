# U1: skills on the status board

From Fasih, for Hamza. Ask A1 in [`docs/FASIH_ASK_2026-11-19.md`](FASIH_ASK_2026-11-19.md); finding U1 in [`docs/HAMZA_REVIEW.md`](HAMZA_REVIEW.md).

**The problem.** `load_board` sorts records by `kind` only. A skill file change shows up under schema changes with no server and no tool, and a skill run shows up as a call to tool `unknown` with outcome `unknown`. Skills have no section of their own, so C1's "every installed skill" is not on screen.

**What this PR adds** (skills side only; nothing under `src/cim/dashboard/` changes):

| Name in `cim.skills.board` | What it is for |
|---|---|
| `is_skill_payload(payload)` | `True` for a record the skills side wrote (`skill_id` is a string). MCP payloads never carry `skill_id`. |
| `skills_board(records)` | Takes the records `load_board` already read and builds the skills section. No second read and no write. |
| `as_dict(board)` | The JSON below. |
| `rail_label(kind, payload)` | `(mark, label)` for a skill record on the fingerprint rail; `None` for an MCP record. |
| `python -m cim.skills board --db S [--json]` | Shows the section before the page does. |

## 1. Shape (version 1)

Values from the demo store in the test report; long paths and hashes shortened with `…`.

```json
{
  "version": 1,
  "warmup": 30,
  "window": 100,
  "summary": {
    "skills": 14, "healthy": 0, "learning": 11, "warning": 3,
    "changed": 2, "removed": 1,
    "changes": 5, "runs": 4, "alerts": 0
  },
  "skills": [
    {
      "skill_id": "word-count",
      "name": "word-count",
      "description": "Count lines, words and characters in a text file.",
      "root": "…/corpus/word-count",
      "state": "warning",
      "alerts": 0,
      "integrity": {
        "state": "changed",
        "baseline_record_id": 14,
        "baseline_ts": "2026-11-23T18:58:23Z",
        "baseline_files": 3,
        "tree_digest": "…64 hex…",
        "files_now": 3,
        "changes": 1,
        "changed_paths": ["SKILL.md"],
        "last_change_ts": "2026-11-23T18:58:23Z"
      },
      "behaviour": {
        "state": "learning",
        "runs": 1,
        "observations": 1,
        "warmed_up": false,
        "last_run_ts": "2026-11-23T18:58:36Z",
        "binaries": [{"value": "…/.venv/bin/python", "runs": 1}],
        "write_targets": [],
        "destinations": [],
        "processes": {"min": 1, "max": 1}
      }
    }
  ],
  "changes": [
    {"record_id": 18, "ts": "…", "skill_id": "word-count", "change": "modify",
     "path": "SKILL.md", "old_path": null, "old_sha256": "…", "new_sha256": "…"}
  ],
  "runs": [
    {"record_id": 22, "ts": "…", "skill_id": "notes-sync", "invocation_id": "…",
     "process_count": 1, "binaries": ["…/python"], "write_targets": [],
     "destinations": ["private_ip:9"], "duration_us": 26283}
  ],
  "alerts": [
    {"record_id": 30, "ts": "…", "skill_id": "notes-sync",
     "code": "skill_behaviour_drift", "detail": "…"}
  ]
}
```

- `skills` is sorted by `skill_id`. `changes`, `runs` and `alerts` are newest first and capped at 40 each. `summary` counts everything, not just the 40.
- `destinations` are `dest_class:port`, as the collector records them. The `runs` count per destination is how many runs in the window showed it.
- No floats anywhere. Wall-clock duration is only in `runs`, never in a profile.
- The key order is fixed by a test (`test_shape_is_stable`). A change to the shape bumps `version`.

## 2. States

The board uses the five states from `docs/DASHBOARD_RESEARCH_NOTES.md`. For December only three apply:

| Field | Values | Rule |
|---|---|---|
| `integrity.state` | `unchanged`, `changed`, `removed` | `removed`: every file of the skill is gone. `changed`: at least one integrity record since the baseline. In FYP I nothing resets this; accepting an update is FYP II (T-31). |
| `behaviour.state` | `empty`, `learning`, `healthy` | `empty`: no runs. `learning`: fewer than 30 runs. `healthy`: 30 or more. |
| `state` (the one to colour) | `warning`, `learning`, `healthy` | `warning` if integrity is not `unchanged` or the skill has an alert. Otherwise `healthy` only when behaviour is warmed up. Otherwise `learning`. |

A skill that has never run is `learning`, never `healthy`. The research notes asked for this: a quiet board during warm-up must not read as a clean bill of health. The page should say "0 of 30" for it.

`alerts` fills in from the shared scorer: `record_behaviour` writes a `skill_behaviour_drift` alert (contract `BehaviourAlertPayload`) for a run that leaves the skill's learned pattern, or `skill_score_failed` if scoring failed. Any `alert` record whose payload has `skill_id` lands here, so the board did not change for it.

## 3. Wiring in `board.py` (yours)

Tested on a throwaway copy of this branch. The full suite passes with it (301 passed); on the demo store from the test report the MCP lists then hold 0 skill records, and the rail reads `json-format: modify SKILL.md`, `word-count: run`.

```diff
 from cim.common.store import BaselineStore
 from cim.mcp.envelope import ToolEnvelope, envelopes
+from cim.skills.board import SkillsBoard, rail_label, skills_board
+from cim.skills.board import as_dict as skills_dict
@@ class Board:
     servers: tuple[str, ...]
     empty: bool
+    skills: SkillsBoard | None = None
@@ def load_board(db: Path) -> Board:
         payload = _object(record.payload)
         if payload is None:
             continue
+        skill_link = rail_label(record.kind, payload)
+        if skill_link is not None:  # a skills record: shown in the skills section (U1)
+            links_all.append(ChainLink(record.id, skill_link[0], skill_link[1], record.ts))
+            continue
         if payload.get("code") == "mcp_pin":
@@
         empty=chain.count == 0 and not patterns,
+        skills=skills_board(records),
     )
@@ def as_dict(board: Board) -> dict[str, Any]:
         "servers": list(board.servers),
+        "skills": skills_dict(board.skills) if board.skills is not None else None,
```

`rail_label` returns the mark `baseline` for a skill's first record. If the page has no style for that mark, map it to `pin`, or add one.

Once `Board` carries `skills`, `test_board_without_the_wiring_still_mislabels_skill_records` skips itself. Delete it then.

## 4. What the page needs (yours)

The minimum for December, from the research notes: one **Skills** block next to the tools, with:
- the summary counts;
- one line per skill: name, `state`, the changed paths when `integrity.state` is not `unchanged`, and "N of 30" while learning;
- skill changes, either in their own list or in the changes list marked as skills.

Runs, profiles and the evidence drawer can wait for FYP II (T-34).

## 5. Questions for Hamza

1. Is this shape enough to build the block, or do you want fields added or renamed? Agree or change it before you wire it; after that it is version 1.
2. Should skill changes stay a separate list, or should the board merge them with MCP schema changes into one timeline? The shape supports both.

**Answered 2026-11-24 (Hamza):** shape accepted as version 1. Skill changes stay a **separate** list on the page (and MCP changes stay MCP-only). Wired in `cim.dashboard.board` / `page`.
