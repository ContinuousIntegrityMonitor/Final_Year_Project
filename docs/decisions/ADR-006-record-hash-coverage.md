# ADR-006: What the record hash covers (S2)

- **Date:** 2026-11-24
- **Status:** Proposed. Needs both members: it changes the formula in plan section 4.7 and every stored hash.
- **Proposed by:** Fasih
- **Finding:** S2 in [`docs/HAMZA_REVIEW.md`](../HAMZA_REVIEW.md); ask A3 in [`docs/FASIH_ASK_2026-11-19.md`](../FASIH_ASK_2026-11-19.md).

## Context

Today, in `cim/common/chain.py`:

```
record_hash = SHA256(prev_hash || kind || canonical_json(payload))
```

Three things a record means are not covered:

| Not covered | So an edit can | Example |
|---|---|---|
| `record.ts` | re-date a record | a schema change "happened" before the approval |
| `record.artefact_id` | move a record to another tool or skill | an alert now belongs to a harmless tool |
| the `artefact` row (`type`, `name`, `origin`) | rename what a record is about | `shout` becomes `not-shout` from `elsewhere` |

Reproduced on `main` at `a816817` (2026-11-24), on the store from the MCP test report. Record 10 is a `shout` call; artefact 2 is the tool `add`:

```sql
UPDATE record   SET ts = '1999-01-01T00:00:00Z', artefact_id = 2 WHERE id = 10;
UPDATE artefact SET name = 'not-shout', origin = 'elsewhere' WHERE id = 3;
```

```
$ cim verify-chain --db s.sqlite --expect-tip b49553a0…485f
verify-chain: ok (42 records) tip=b49553a0…485f        exit 0
```

The tip hash does not move, so even the outside anchor from Stage 1 (`--expect-tip`, `--min-count`) cannot see it. SYS-14 says any historical edit breaks the chain.

A smaller point: the three fields are joined with no separator. It is not exploitable today, because `kind` comes from a fixed set and the payload always starts with `{`, but the encoding should be unambiguous by construction, not by luck.

## Options

1. **Leave it.** Write in the threat model that `ts` and attribution are unprotected. Cheapest, but it weakens C5 and A5 exactly where the demo claims strength.
2. **Hash the record's own columns** (`artefact_id`, `ts`) but not the artefact row. Closes re-dating and moving; a renamed artefact still passes.
3. **Hash the record's columns and its artefact row** (proposed). Each record also covers the `type`, `name` and `origin` of the artefact it belongs to, so renaming an artefact breaks every record about it.
4. **Chain the artefact table as well**, as records of a new kind. This also covers artefact rows that no record refers to, but those carry no evidence, and it adds a record kind to the contract.

## Proposal (option 3)

```
record_hash = SHA256( canonical_json([
    "cim-record/2",     # version tag: a v1 hash can never equal a v2 hash
    prev_hash,
    artefact_id,        # integer
    artefact_type, artefact_name, artefact_origin,
    kind,
    ts,
    payload_canonical,  # the stored payload text, as a JSON string
]) )
```

- A JSON array through the existing `canonical_json` is the separator: every field is quoted or a number, so no two field lists encode the same way. No new encoding code.
- `record.id` stays out: `verify_chain` already requires ids 1, 2, 3, … with no gap, and `prev_hash` fixes the order.
- `envelope_obs` (test report M1) is a separate fix: the scorer design proposes moving those fields into the chained payload (contract v1.1).

### Versions and existing stores

- A new table `store_meta(key TEXT PRIMARY KEY, value TEXT)` holds `hash_version = 2`. It is written when a store is created.
- A store without `store_meta` is version 1.
  - `verify-chain` still verifies it with the v1 formula and says so: `ok (42 records, hash v1: ts and artefacts not covered)`. Old evidence stays checkable.
  - `append_record` refuses to write to it. One chain never mixes two formulas.
- **Migration: none. Existing stores are throwaway.**
  - Nothing has run on VM-MON.
  - Every store so far is a lab or test store (`docs/HAMZA_REVIEW.md` already says baselines written before S2 is settled are throwaway; so do the T-08 and T-11 progress notes).
  - Re-hashing an old store would also re-sign whatever edits it may already contain, so a converter would be worse than nothing.
  - Hamza: if you have stores on your PC you want to keep (`logs/cursor-playwright.sqlite`, `logs/cursor-http.sqlite`), say so. They keep verifying as v1; they just cannot be appended to.

### What changes in code

| File | Change | Territory |
|---|---|---|
| `src/cim/common/chain.py` | `compute_record_hash` takes the new fields; version tag | border (both review) |
| `src/cim/common/store/baseline.py` | `store_meta`; append reads the artefact row inside its transaction; verify joins it; v1 stores verify read-only | border, implemented by Hamza (T-06) |
| `src/cim/common/schema/canonical.py` | docstring formula | border |
| `src/cim/dashboard/call_demo.py` | `tamper_log` recomputes a hash with the old arguments | Hamza |
| `tests/common/test_chain.py`, `tests/common/test_store.py`, `tests/common/test_schema_envelope.py` | new formula, and one test per row of the table above: re-date, move and rename each break the chain; a v1 store verifies and refuses appends | joint |
| plan section 4.7, `docs/THREAT_MODEL.md` 6.3 | formula and claim | joint |

Cost: one artefact lookup per append (inside the transaction that already runs) and one join in `verify_chain`. Negligible at lab size.

## Consequences

- Re-dating, moving or renaming an artefact breaks the chain at the first record it touches, and the tip changes, so `--expect-tip` catches it too.
- The chain still proves consistency, not authenticity: anyone who can write the file can rebuild a whole new chain. The outside anchor (`--expect-tip`) and, in Phase 2, the off-host verifier (T-27) are what catch that.
- Every store created before the change is a v1 store.

## Decision needed

1. Option 3, or another option.
2. The formula as written, including the version tag and the JSON-array encoding.
3. No migration, with v1 stores read-only.
4. Who implements it. The store is yours (T-06); Fasih can prepare the PR if you pre-agree.
