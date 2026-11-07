# CIM — Continuous Integrity Monitor

Final Year Project (ITU Lahore, 2026–2027). Monorepo for MCP-side (Hamza) and skills-side (Fasih) security monitoring.

Plan document: [`docs/plan/Final_Year_Project_Latest.pdf`](docs/plan/Final_Year_Project_Latest.pdf)

**Status:** [`PROJECT_STATUS.md`](PROJECT_STATUS.md) · **Decisions:** [`DECISIONS.md`](DECISIONS.md) · **Context:** [`CONTEXT.md`](CONTEXT.md)

## Members

| Role | GitHub |
|------|--------|
| Hamza Farooq (MCP) | [@HamzaFarooq3333](https://github.com/HamzaFarooq3333) |
| Fasih (Skills) | [@fasih-moin](https://github.com/fasih-moin) |

Org / committee home: [ContinuousIntegrityMonitor/Final_Year_Project](https://github.com/ContinuousIntegrityMonitor/Final_Year_Project)  
Day-to-day + PR history: [HamzaFarooq3333/Final_Year_Project](https://github.com/HamzaFarooq3333/Final_Year_Project)

Either member may push from their own laptop. Every push runs **ci-push**; every PR to `main` runs **merge-gate**. Push accepted work to **both** remotes (ADR-002).

## Quick start (Linux or WSL2 Ubuntu)

```bash
git clone https://github.com/HamzaFarooq3333/Final_Year_Project.git
cd Final_Year_Project
git remote add org https://github.com/ContinuousIntegrityMonitor/Final_Year_Project.git
# Install uv: https://docs.astral.sh/uv/
bash scripts/bootstrap.sh
source .venv/bin/activate
bash scripts/check-env.sh --dev
pytest -m "not lab"
```

Windows: develop inside **WSL2 Ubuntu** (Docker/cgroups need Linux). Install **Docker Engine + CLI inside Ubuntu** (not Docker Desktop). Verify with `docker run --rm hello-world`.

### Fasih (other laptop)

1. Accept the GitHub collaborator invite (personal and/or org).
2. Clone on Linux or WSL2 Ubuntu; add the `org` remote as above.
3. Run `scripts/bootstrap.sh` then `scripts/check-env.sh --dev`.
4. Work on a task branch `tXX-slug`, push, open a PR titled `T-XX: ...`.
5. CI evaluates your push the same as Hamza’s — no special setup beyond write access.

## Workflows

- `.github/workflows/ci-push.yml` — every push, every branch
- `.github/workflows/merge-gate.yml` — PRs to `main` (title lint, DIRECTORY freshness, sys tests)

Same workflow files ship to both remotes so the org repo runs the same pipeline after the first push.

## Layout

See [`DIRECTORY.md`](DIRECTORY.md) (generated) and [`CONTEXT.md`](CONTEXT.md). Agent skill names used in this workspace: [`docs/SKILLS_MANIFEST.txt`](docs/SKILLS_MANIFEST.txt).

