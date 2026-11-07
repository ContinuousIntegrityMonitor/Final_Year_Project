# ADR-003: FYP I December scope

- **Date:** 2026-11-07
- **Status:** Accepted
- **Decided by:** Hamza Farooq (Fasih temporarily unavailable; MCP path led by Hamza)

## Context

FYP I committee readiness target ~1 Dec 2026. Full product polish (UI, cloud ops, Missing Semester extras) does not fit before that date if the functional SEE path is incomplete.

## Options considered

1. Stretch for a polished product demo by Dec (high miss risk)
2. **Ship a functional SEE path for Dec; defer polish to FYP II** (chosen)

## Decision — FYP I (by ~1 Dec 2026)

Must show:

- End-to-end MCP SEE path: lab harness (T-04) → baseline store (T-06) → capture / integrity signals toward C1–C5
- Living progress (`progress/`), decisions (`DECISIONS.md` + `docs/decisions/`), dual remotes + green CI
- Org Gmail / project identity: `fyp26_cim@gmail.com` for ContinuousIntegrityMonitor

Defer to FYP II (post-Dec / Apr 2027 demo):

- Product polish, cloud deployment, Missing Semester depth, skills-side full behavioural path completeness beyond what Fasih lands for Dec

## Consequences

Prioritise T-06 merge (after Fasih review), then T-07/T-09 MCP path. Do not invent unrequested features. Progress files stay the source of task truth.
