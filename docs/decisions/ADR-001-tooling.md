# ADR-001: Tooling decisions (T-01)

- **Date:** 2026-10-03
- **Status:** Accepted
- **Decided by:** Hamza Farooq (MCP lead); Fasih Moin informed

## Context

Need one reproducible toolchain for both members and CI (plan §4.5).

## Options considered

1. pip + requirements.txt + system Python
2. Poetry / Conda
3. **uv + pyproject.toml + committed uv.lock** (chosen)

## Decision

- Python 3.12, package name `cim`, src-layout
- `uv` for venvs and locked deps; never global `pip`
- Ruff + mypy + pytest + pre-commit (ruff + gitleaks)
- GitHub Actions: `ci-push` + `merge-gate` (same workflows on personal and org remotes)
- Dev on Linux or WSL2 Ubuntu; Docker Engine + CLI inside Ubuntu (not Docker Desktop)

## Consequences

Both machines and CI install from the same lockfile. Dependency changes are one-per-PR and announced at weekly sync.
