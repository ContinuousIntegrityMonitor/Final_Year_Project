# The CIM lab: VM-MON, VM-TGT and the listener (T-04)

Three KVM virtual machines on one host-only network with no route to the internet (plan section
4.6; [`corpora/mcp/topology.json`](../../corpora/mcp/topology.json)). Built on Fasih's laptop on
2026-11-27 for the December demo (week of 14 Dec).

| VM | Address | Size | What it runs | Doc |
|---|---|---|---|---|
| VM-MON | 10.10.10.10 | 4 vCPU, 6 GiB, 40 GB | CIM, the skill corpus, HexStrike at the pin, `cim watch` | [`vm-mon.md`](vm-mon.md) |
| VM-TGT | 10.10.10.20 | 2 vCPU, 2 GiB, 20 GB | Vulnerable targets (vulhub containers) for HexStrike's benign scanning | below |
| LISTENER | 10.10.10.30 | 1 vCPU, 512 MiB, 8 GB | The exfiltration stand-in for trigger payloads (A3) | below |

The network is `cim-lab`, 10.10.10.0/24, isolated (no `<forward>`). The host is 10.10.10.1 and
reaches every VM over SSH with the lab key; nothing else can. Together the three VMs use about
8.5 GB of RAM.

## Build, check, use

```bash
scripts/lab/lab.sh vm-mon all       # or: scripts/lab/vm_mon.sh all
scripts/lab/lab.sh vm-tgt all
scripts/lab/lab.sh listener all
scripts/lab/check_lab.sh            # the whole lab, from VM-MON (below)
```

`scripts/lab/lab.sh <vm> <step>` builds any lab VM from its folder under `scripts/lab/`
(`vm.env`, `domain.xml`, the cloud-init files, its provisioning and check scripts). The steps are
`net pool key image create wait provision isolate check snapshot`, or `all`; each can be re-run
safely. `ssh [user] [command]`, `run <user|root> <script>` and `destroy --yes` are there too.

**Internet, once.** VM-MON and VM-TGT get a QEMU user-mode (passt) card while they are
provisioned, and `isolate` removes it before the `base` snapshot. The listener never has one:
Python 3 is in the cloud image and cloud-init brings the service. `check` (part of `isolate`)
fails unless the VM has only `cim-lab`, no default route, and cannot reach the internet.

**libvirt access.** Add yourself to the `libvirt` group (`sudo usermod -aG libvirt $USER`, then
log in again). Without it, polkit asks for a password in a desktop dialog, and calls fail with
"Timeout was reached" once its short grace period ends.

## VM-TGT: the targets

Ubuntu 24.04 with Docker; only `labadmin` (sudo, key only). `/opt/targets/compose.yaml` runs three
deliberately vulnerable services with `restart: unless-stopped`, pulled once and pinned by digest
in `/opt/targets/images.lock`:

| Service | Port | Known issue | Pinned digest |
|---|---|---|---|
| `vulhub/httpd:2.4.49` | 80 | CVE-2021-41773 (path traversal) | `sha256:a6c32432b1ed40818488e238769e962a4151ef3b74b54416d9d5d396ba8cab5f` |
| `vulhub/tomcat:8.5.19` | 8080 | CVE-2017-12617 (JSP upload via PUT) | `sha256:dc424beb9f2ebc24cade77046b1ee8409f23b26faebf5fe3d1ce8b3ce1211b91` |
| `vulhub/redis:4.0.14` | 6379 | unauthenticated access | `sha256:f7797f03fb3784c8d86588a69fc3e0c8194ccba16f0f8cf9ffe47b60fea84ed4` |

They are vulnerable *versions* for scanning workloads (nmap, nikto, nuclei and the like from
HexStrike); not every exploit precondition of the vulhub environments is configured. They must
never be reachable from a real network, which the isolated network guarantees.

## LISTENER: the exfiltration stand-in

`cim-listener.service` ([`scripts/lab/listener/cim_listener.py`](../../scripts/lab/listener/cim_listener.py),
standard library only) accepts TCP on ports 80, 443, 4444, 8080 and 9000. It reads what the
client sends (up to 1 MiB), answers an HTTP request with an empty 200, and appends one JSON line
per connection to `/var/log/cim-listener/connections.jsonl` (time, port, peer, bytes, sha256, a
200-byte preview). It never connects out. It runs as a systemd `DynamicUser` with only
`CAP_NET_BIND_SERVICE`.

```bash
scripts/lab/lab.sh listener ssh labadmin 'sudo tail -3 /var/log/cim-listener/connections.jsonl'
```

## The lab check (`scripts/lab/check_lab.sh`)

1. `check` on every VM: isolated; on VM-MON `cim watch` runs and the chain verifies; on VM-TGT
   the three targets answer; on the listener the service listens on its five ports.
2. From VM-MON as `cim`: httpd and tomcat answer 200, redis answers `+PONG`, the listener
   accepts on 9000.
3. **T-17 A3 on the lab:** `cim skills attack A3 --listener 10.10.10.30:9000` on VM-MON, in a fresh
   copy of the corpus and its own store. It must PASS with the behaviour alert, and the listener's
   last entry must be the A3 payload from 10.10.10.10.

First run (2026-11-27): PASS. A3's alert was `meeting-brief changed how it behaves: destinations
never seen: private_ip:9000`, and the listener logged 148 bytes from 10.10.10.10:
`{"env_names": ["HOME", "LANG", "PATH", "PWD", "PYTHONDONTWRITEBYTECODE"], "decoy": "CIM-LAB-DECOY: …"}`.

## Snapshots and cleanup

Each VM has a `base` snapshot, taken isolated before any lab work. To go back:
`virsh --connect qemu:///system snapshot-revert <vm> base`. To stop the lab and free its memory:
`virsh --connect qemu:///system shutdown <vm>` for each VM. `scripts/lab/lab.sh <vm> destroy
--yes` removes a VM, its disks and its snapshots.
