# ADR-007: The boundary between skill helpers and the monitor (T-11)

- **Date:** 2026-11-24
- **Status:** Accepted for the skills side (Fasih, T-11 owner). Part 2 changes how `cim proxy` and `cim skills exec` write events, so decision 8 of the T-13 design note needs Hamza's agreement before T-13 is built.
- **Decided by:** Fasih
- **Closes:** the open decision in `docs/THREAT_MODEL.md` 6.2 and in `progress/tasks/T-11.md`.

## Context

The helper, its tracer (`strace`), the trace file, its cgroup scope and the evidence store all belong to one user. Checked on the dev laptop (2026-11-24): the user's cgroup subtree `user@1000.service` and its `cgroup.procs` are owned by `fasih`, and the trace file is written in a temp directory `fasih` can write.

So a helper that actively evades the monitor can:

| | How | Where it is noted |
|---|---|---|
| Leave its scope: no longer attributed, not killed at the end | write its PID into another cgroup of its own user's subtree | `scoped.py` |
| Edit its trace file, or kill the tracer | same user | `collector.py` |
| Notice it is traced, and behave well | `TracerPid` in `/proc/self/status` | `collector.py` |
| Edit the store | the store file belongs to the same user (adversary AD3) | threat model 6.3 |

The December demo is not affected: the T-17 A3 helper changes behaviour on a trigger word but does not evade.

## Options

| Option | Closes | Leaves open | Cost |
|---|---|---|---|
| A. Keep one user; word the claim precisely | nothing | all four | none |
| B. Run helpers as a separate unprivileged user | scope escape, trace tampering | detection, store | medium: root to switch user. A helper can no longer read the operator's files, which real skills exist to work on, and adversary AD2 changes meaning |
| C. Run the monitor and store as their own `cim` user; helpers keep running as the operator | scope escape, trace tampering, killing the tracer, editing the store | detection | larger: a small root-owned launcher, and one store writer that wrappers send events to |
| D. eBPF or audit events instead of `strace` | all four | a root attacker | high: new tooling and attribution logic |

How C closes the gaps:
- **The scope is created at system level by a root-owned launcher**, so its cgroup belongs to root. cgroup v2 only lets a process move if the writer can write the `cgroup.procs` of the common ancestor of both cgroups, and here that is root's. The move is refused.
- **The launcher runs the tracer as root, `strace -u <operator>`** (strace 7.3 has `-u`). So the helper still runs as the operator, with the operator's files and behaviour.
- **The trace directory and the store belong to the `cim` user.** The helper cannot write them, and cannot signal the tracer or the monitor.

## Decision

1. **FYP I (December): option A.** Nothing changes in how helpers run. The claim is worded as:

   > Behaviour is attributed per invocation and cannot be missed by a short-lived process. Against a helper that actively evades the monitor (leaving its cgroup, tampering with its trace), Phase 1 gives no guarantee: helpers and the monitor share one user. Phase 2 separates them.

2. **FYP II: option C.** It fits work Phase 2 needs anyway:
   - T-29 / T-30 response needs privileged actions (refusing a call, moving a skill away).
   - T-26 / T-27 attestation treats the monitor as its own protected component.
   - It closes store editing by code running as the operator (A5), which the hash chain alone cannot.

3. **If T-33 (April) needs tracer detection closed as well, replace `strace` with eBPF (option D)** inside the option C layout; nothing else in C changes.

4. **Now, in T-13:** `cim proxy` and `cim skills exec` should not keep opening the store themselves. In the long run they send events to one store writer that `cim watch` runs; in Phase 2 that writer is the only process running as `cim`. This is decision 8 of `docs/T13_PIPELINE_DESIGN.md`, for Hamza. For December the wrappers may still write directly, as today, as long as the code goes through one function that can later become the client.

## Consequences

- Nothing in the December build changes; the threat model (6.2) and the demo script use the wording in decision 1.
- Phase 2 needs root on the monitored host to install the launcher and the `cim` user. That is acceptable on VM-MON.
- After C, the remaining gaps are tracer detection (until eBPF) and a root or kernel attacker (T-26 / T-27).
