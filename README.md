# CIM — Continuous Integrity Monitor

Final Year Project (ITU Lahore, 2026–2027). Monorepo for MCP-side (Hamza) and skills-side (Fasih) security monitoring.

Plan document: [`docs/plan/Final_Year_Project_Latest.pdf`](docs/plan/Final_Year_Project_Latest.pdf)

## Members

| Role | GitHub |
|------|--------|
| Hamza Farooq (MCP) | [@HamzaFarooq3333](https://github.com/HamzaFarooq3333) |
| Fasih (Skills) | [@fasih-moin](https://github.com/fasih-moin) |

Either member may push from their own laptop. Every push runs **ci-push**; every PR to `main` runs **merge-gate**.

## Quick start (Linux or WSL2 Ubuntu)

```bash
git clone https://github.com/HamzaFarooq3333/Final_Year_Project.git
cd Final_Year_Project
# Install uv: https://docs.astral.sh/uv/
bash scripts/bootstrap.sh
source .venv/bin/activate
bash scripts/check-env.sh --dev
pytest -m "not lab"
```

Windows: develop inside **WSL2 Ubuntu** (Docker/cgroups need Linux). Install **Docker Engine + CLI inside Ubuntu** (not Docker Desktop). Verify with `docker run --rm hello-world`.

### Fasih (other laptop)

1. Accept the GitHub collaborator invite.
2. Clone the repo on Linux or WSL2 Ubuntu.
3. Run `scripts/bootstrap.sh` then `scripts/check-env.sh --dev`.
4. Work on a task branch `tXX-slug`, push, open a PR titled `T-XX: ...`.
5. CI evaluates your push the same as Hamza’s — no special setup on GitHub beyond write access.

## Workflows

- `.github/workflows/ci-push.yml` — every push, every branch
- `.github/workflows/merge-gate.yml` — PRs to `main` (title lint, DIRECTORY freshness, sys tests)

## Layout

See [`DIRECTORY.md`](DIRECTORY.md) (generated) and [`CONTEXT.md`](CONTEXT.md).
