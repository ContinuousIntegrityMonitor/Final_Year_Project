# CIM setup status (Hamza machine)

Last updated: 2026-10-04 — T-01 remnants completed (public repo, branch protection, Ubuntu bootstrap)

## Done

| Item | Status | Verified how |
|------|--------|--------------|
| Git repo + remote | OK | `origin` → HamzaFarooq3333/Final_Year_Project |
| Monorepo scaffold (T-01) | OK | src-layout `cim`, scripts, templates, plan PDF in `docs/plan/` |
| Dual GitHub CI | OK | `ci-push` + `merge-gate` green on [PR #1](https://github.com/HamzaFarooq3333/Final_Year_Project/pull/1) |
| CODEOWNERS | OK | `@HamzaFarooq3333`, `@fasih-moin` |
| Collaborator invite | SENT | `fasih-moin` write — accept on his laptop |
| Python / uv (Windows) | OK | Python 3.12 + `uv` + pytest 26 passed |
| Plan PDF | OK | `docs/plan/Final_Year_Project_Latest.pdf` |
| Corrupt WSL `system.vhd` | FIXED | Replaced truncated 374MB file with good 758MB VHD from MSI extract |
| **Ubuntu 24.04 on D:** | OK | `wsl -l -v` shows `Ubuntu-24.04`; VHD at `D:\WSL\Ubuntu-24.04\ext4.vhdx`; `PRETTY_NAME=Ubuntu 24.04 LTS` |
| C: disk freed | OK | Was ~3GB; now ~9–11GB (still keep heavy data on D:) |

## Docker / Ubuntu (updated)

| Item | Status | Notes |
|------|--------|-------|
| Docker Desktop | REMOVED | Uninstalled; leftovers cleared from C:/D: |
| Docker Engine + CLI | OK **inside Ubuntu WSL** | `docker 29.8.2`, compose v5.6.0; `hello-world` passed |
| Ubuntu-24.04 on D: | OK | `D:\WSL\Ubuntu-24.04` |
| Laptop fit | OK with limits | **7.9 GB RAM** — WSL capped to 3GB via `%UserProfile%\.wslconfig`. Do **not** use Docker Desktop on this machine. |
| Use Docker | From Ubuntu | `wsl -d Ubuntu-24.04` then `sudo dockerd` if needed, then `docker run ...` |

## Still needed

| Item | Status | What you should do |
|------|--------|--------------------|
| Fasih local bootstrap | PENDING HIM | Clone; `wsl`/Linux + `scripts/bootstrap.sh` + Docker Engine |
| Optional fail-gate drill | Optional | Deliberate bad PR title / lint fail to demo gates |

## Completed this session

| Item | Status |
|------|--------|
| Repo public | OK |
| Branch protection on `main` | OK (merge-gate + 1 review + CODEOWNERS) |
| PR #1 T-01 scaffold | MERGED |
| SETUP_STATUS docs | MERGED (PR #3) |
| Ubuntu bootstrap at `/home/hamza/cim` | OK |
| `check-env.sh --dev` | OK |

### Paths on D:

- `D:\WSL\Ubuntu-24.04` — Ubuntu VHDX  
- `D:\WSL\downloads\` — rootfs, WSL MSI, `bootstrap-cim.sh`  
- `D:\DockerData` — intended Docker data folder  
- `D:\Temp` — install temp

## Not needed yet (Phase 2 / later tasks)

- Ollama, QEMU/swtpm, HexStrike lab VMs, scanner API keys

## API keys

None required for T-01.
