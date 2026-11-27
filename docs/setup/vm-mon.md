# VM-MON: the CIM lab's monitored host (T-04)

VM-MON is the machine the December demo runs on (plan section 4.6;
[`corpora/mcp/topology.json`](../../corpora/mcp/topology.json)). It is a KVM virtual machine on
Fasih's laptop, on a host-only lab network with no route to the internet, and it runs CIM, the
seed skill corpus and HexStrike AI at the pinned commit. Once it is up, everything on it follows
[`cim-pipeline.md`](cim-pipeline.md).

VM-TGT (the targets, 10.10.10.20) and the listener (10.10.10.30) are in [`lab.md`](lab.md), with the lab-wide check. `scripts/lab/vm_mon.sh` is `scripts/lab/lab.sh vm-mon`, plus the `hexstrike` check.

## What gets built

| Piece | Value |
|---|---|
| Lab network | `cim-lab`, 10.10.10.0/24, isolated (no `<forward>`); the host is 10.10.10.1 |
| VM | `vm-mon`: Ubuntu 24.04 cloud image, 4 vCPU, 6 GiB RAM, 40 GB disk, 10.10.10.10 |
| Users | `labadmin`: administration, sudo, SSH key only. `cim`: the operator. Agents, skills, MCP servers and CIM run as `cim`, which has **no sudo**, so a skill acting as the operator cannot become root |
| Skills | the seed corpus in `/opt/skills`, owned by `cim` |
| HexStrike | `/opt/mcp/hexstrike` at the commit in [`corpora/mcp/hexstrike.pin`](../../corpora/mcp/hexstrike.pin), with its own virtualenv |
| CIM | `~cim/cim` (this repo), `~cim/cim.toml`, store `~cim/cim-data/cim-store.sqlite`, `cim watch` as a systemd user unit (`cim-watch.service`, with linger) |
| Snapshot | `base`: built and isolated, before any lab work |

The VM needs the internet once, to install packages, uv, HexStrike's requirements and CIM. A
second network card is attached for that, and `isolate` removes it before the `base` snapshot,
so the finished VM is on `cim-lab` alone. That card is QEMU user-mode networking (passt), not
libvirt's NAT network: with Docker installed on the host, Docker sets the `FORWARD` chain to drop
and libvirt's NAT silently goes nowhere (found on the first build, 2026-11-27). passt opens the
connections from the QEMU process itself, so it works without root or a firewall change.

## Requirements on the host

- Linux with KVM (`/dev/kvm`) and libvirt (`virsh`), and your user allowed to manage
  `qemu:///system` by polkit (Fedora: in `wheel` or `libvirt`). No sudo is needed after that.
- `genisoimage`, `curl`, `ssh`.
- About 7 GB of RAM and 10 GB of disk free.

## Build it

```bash
scripts/lab/vm_mon.sh all       # about 15 minutes, most of it the first boot and installs
```

`all` runs these steps in order; each one can also be run alone, and is safe to re-run:

| Step | What it does |
|---|---|
| `net` | Defines and starts `cim-lab`; refuses a network with a `<forward>` |
| `pool` | A libvirt storage pool at `/var/lib/libvirt/images/cim-lab` |
| `key` | A lab-only SSH key, `~/.ssh/cim_lab_ed25519` |
| `image` | Downloads the Ubuntu 24.04 cloud image (resumable), checks it against Ubuntu's `SHA256SUMS`, uploads it as the base volume |
| `create` | Writes the cloud-init seed, makes the 40 GB overlay disk, defines and starts `vm-mon` |
| `wait` | Waits for SSH and for cloud-init to finish |
| `provision` | As root (through `labadmin`): `/opt/skills`, `/opt/mcp`, HexStrike at the pin. As `cim`: uv, CIM, the skills, `cim.toml`, the first inventory, `cim watch` |
| `isolate` | Removes the NAT card, then `check` |
| `check` | Only `cim-lab` attached; no default route; no way out to the internet; `cim status --require-watch` |
| `snapshot` | `base` (or a name you give) |
| `hexstrike` | Not part of `all`: starts HexStrike's API server, lists its tools through `cim proxy` (T-04 acceptance: 150 or more), and stops it again. Run after `base`, since it writes records |

Until T-13's last two PRs (#58, #59) are on `main`, build from that branch, because `cim watch`
is not on `main` yet:

```bash
CIM_REPO_REF=t13-acceptance scripts/lab/vm_mon.sh all
```

## What was built (2026-11-27)

The first build, on Fasih's laptop (Fedora 44, libvirt 12, QEMU 10.2):

| Item | Value |
|---|---|
| Base image | Ubuntu 24.04 cloud image, sha256 `04e8f2461a16a44e78a370284471f29616cdd9baf1893df25807b71f985b6c94` |
| CIM | `t13-acceptance` @ `a931efe` (`cim watch` is not on `main` yet) |
| HexStrike | `d689933ff579d839c676c82b231f8e98326c5f04`, at the pin |
| Isolation | only `cim-lab` attached, no default route, `curl https://github.com` fails |
| CIM state | 15 skills baselined; `cim watch` running under systemd (`cim-watch.service`); chain ok |
| Snapshot | `base`, taken isolated with a clean store (15 records) |
| After `base` | `hexstrike`: **150 tools** listed through `cim proxy`, `cim status` shows 1 server with 150 tools; one `cim skills exec` run of word-count traced and recorded; `cim status --require-watch` exit 0 |

The first boot's package installs failed (libvirt's NAT network was blocked by the host's Docker
rules); the build switched the NAT card to passt and re-ran them in `provision`. The scripts now
use passt from the start, but a from-scratch rebuild with them has not been timed yet.

## Use it

```bash
scripts/lab/vm_mon.sh ssh cim                      # a shell as the operator
scripts/lab/vm_mon.sh ssh cim 'cd ~ && ~/.local/bin/uv run --project ~/cim cim status'
scripts/lab/vm_mon.sh ssh labadmin                 # administration (sudo)
scripts/lab/vm_mon.sh check                        # isolation + CIM, any time
```

Back to the clean state, and after lab work, a new snapshot:

```bash
virsh --connect qemu:///system snapshot-revert vm-mon base
scripts/lab/vm_mon.sh snapshot week-2026-12-07
```

To update CIM on VM-MON later, it needs the internet again: attach a NAT card for the update,
then run `isolate` and take a new snapshot.

## Remove it

```bash
scripts/lab/vm_mon.sh destroy --yes    # the VM, its disks, its snapshots and cim-lab
```

The downloaded image (`~/.cache/cim-lab`) and the storage pool are kept, so a rebuild skips the
download.
