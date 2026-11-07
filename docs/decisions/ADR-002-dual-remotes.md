# ADR-002: Dual GitHub remotes (personal + org)

- **Date:** 2026-11-07
- **Status:** Accepted (URL corrected 2026-11-07)
- **Decided by:** Hamza Farooq

## Context

Work started on the personal repo `HamzaFarooq3333/Final_Year_Project`. The committee-facing project home is the org repo `ContinuousIntegrityMonitor/Final_Year_Project`. An earlier hyphenated name (`Final-Year-Project`) was abandoned; do not use it.

## Options considered

1. Move entirely to the org repo and abandon the personal remote
2. Keep only the personal remote and link the org as a mirror later
3. **Dual remotes: push the same branches/commits to both** (chosen)

## Decision

- `origin` → `https://github.com/HamzaFarooq3333/Final_Year_Project.git` (day-to-day + existing PRs/Actions history)
- `org` → `https://github.com/ContinuousIntegrityMonitor/Final_Year_Project.git` (committee / project home)
- After each accepted phase (or docs sync), push the same refs to **both** remotes
- Run local CI gates (ruff, mypy, pytest, script help, check-env) **before** pushing so org/Actions stay green
- CI workflows already in-tree (`.github/workflows/ci-push.yml`, `merge-gate.yml`) apply on both once Actions is enabled for the org repo
- Existing open PRs (e.g. T-06 #163) stay on `origin` until Fasih reviews; mirror the branch to `org` for backup/visibility

## Consequences

Two remotes to keep in sync. Prefer `git push origin <ref>` then `git push org <ref>`. Do not rewrite history on either remote.
