# T-18: skills part of the December demo (runbook)

- **Covers:** the skills part only. The plan (T-18) has Hamza drive the 10-minute demo and Fasih run the skills beat. Hamza's MCP beats appear here only as **HAND-OVER** points; what happens in them is his to write.
- **Script:** [`scripts/demo_skills_beat.sh`](../../scripts/demo_skills_beat.sh). It runs each step on cue, checks the result and prints `OK` or `FAIL`.
- **Plan references:** T-18 (section 6), the December checklist (section 12) and C1 to C6 (section 2.1) in `docs/plan/Final_Year_Project_Latest.pdf`.
- **Rehearsed:** twice end to end on Fasih's laptop (Fedora 44), and twice on VM-MON against the lab listener, 2026-11-27. All four passed (section 5). **Not rehearsed:** with HexStrike, with Hamza's MCP beats, with an audience or a projector. The backup video is not recorded. Section 6 has the full list.

## 1. What the skills beat shows

| Step | What the audience sees | Criterion |
|---|---|---|
| `reset` | Fresh workspace: a copy of the 15-skill corpus checked against its manifest, a `cim.toml`, an empty store | setup (done before going on stage) |
| `inventory` | `cim inventory` baselines all 15 installed skills; the dashboard Skills panel lists them, all "0 of 30" | **C1** (skills half) |
| `watch` | `cim watch` starts the skills watcher; `cim status` shows it running | setup for the integrity step and C5 |
| `warmup` | 30 traced runs each of `meeting-brief` and `word-count` through `cim skills exec` (the agent-harness path), sped up; the board goes from learning to warmed up | **C2-style capture**, skills side: every run captured and visible |
| `tamper` | One line appended to an installed helper; the watcher records it within a second | integrity (T-10); the skills counterpart of C3's "an artefact changed" |
| `a3` | T-17 A3: `meeting-brief` reads notes that mention "quarterly" and sends environment variable *names* out. The behaviour alert names the never-seen destination, and the skill's file hashes are shown identical before and after | **C4**, skills side (the plan's stretch beat) |
| `a4` | T-17 A4: a legitimate update of `word-count` is recorded as two file changes, and the next run raises no behaviour alert | false-positive control |
| `status` | `cim status` (2 changed skills, 1 behaviour alert), the events, the dashboard in warning, `cim verify-chain` ok | **C5** |

C6 (backup video, demo script committed): this runbook and the script are the skills half of "demo script committed". The video is not recorded (section 6).

## 2. Where it fits in the 10 minutes

The plan's section 12 order, with the skills steps placed next to the MCP beat they echo. **The minute marks are a proposal for Hamza, who drives and decides the running order.** The skills steps total about 4 minutes of talking. The machine time is about 23 s, nearly all of it the sped-up warm-up.

| Time | Plan item (section 12) | Who | What |
|---|---|---|---|
| 0:00–0:20 | | Hamza | Opening |
| 0:20–1:00 | 1. Fresh boot: `cim inventory` (C1) | Hamza | **HAND-OVER (Hamza):** HexStrike tools with schema digests |
| 1:00–1:40 | 1. (skills half) | Fasih | `inventory` |
| 1:40–3:10 | 2. Live benign session, call log, warm-up counter (C2) | Hamza | **HAND-OVER (Hamza):** benign HexStrike session through `cim proxy` |
| 3:10–4:00 | 2. (skills half) | Fasih | `watch`, `warmup` |
| 4:00–5:15 | 3. Rug pull → schema-drift alert with diff (C3) | Hamza | **HAND-OVER (Hamza):** A1 / backdoored server |
| 5:15–5:40 | 3. (skills half) | Fasih | `tamper` |
| 5:40–6:40 | 4. Trigger tool → behavioural alert, hash unchanged (C4) | Hamza | **HAND-OVER (Hamza):** A2, MCP trigger tool |
| 6:40–7:40 | 4. (skills half) | Fasih | `a3` |
| 7:40–8:10 | | Fasih | `a4` |
| 8:10–8:45 | 5. `cim status` + alert summary; verify-chain (C5) | Fasih, then Hamza | `status` (skills store); **HAND-OVER (Hamza):** his store's status |
| 8:45–10:00 | 6. Q&A | both | Dashboard stays up; `stop` afterwards |

**Open for Hamza (not decided here):**
1. **One store or two.** The script keeps its own store (`<work>/store.sqlite`), so `cim status` in the `status` step shows skills only. If both sides should appear in one `cim status` and one dashboard (C5 says "shows inventory, events, alerts"), the script needs a way to use a shared `cim.toml`. Not built; say if you want it.
2. **Dashboard port.** The script uses 8766 so it never takes 8765, the default your MCP beats would use. With one store, one dashboard would do.
3. **Running order.** Interleaved as above, or all the skills steps in one block after C4.

## 3. Before going on stage

About 10 minutes before. Run as the operator (on VM-MON: `cim`), in a real login session.

```bash
systemctl --user is-system-running   # "running" or "degraded": a user session exists
strace -V | head -1                  # strace is installed
cd ~/cim                             # the CIM checkout (on the laptop: the repo)
scripts/demo_skills_beat.sh --no-pause && scripts/demo_skills_beat.sh stop   # a full dry run
scripts/demo_skills_beat.sh reset    # fresh workspace for the stage run
```

- Use a terminal at least 120 columns wide, with a large font. To shorten the paths on screen, pass `--work ~/demo` to **every** call.
- On VM-MON, add `--listener 10.10.10.30:9000 --origin vm-mon` to every call (section 4).
- The workspace is `~/.cache/cim-demo/skills-beat` unless `--work` or `$CIM_DEMO_WORK` says otherwise. `reset` deletes it and starts again. It refuses a folder it did not make, the repo, and anything inside the corpus.
- The script only ever **reads** `corpora/skills/`. Every write goes to the copy in the workspace.

On stage, either run `scripts/demo_skills_beat.sh inventory watch warmup tamper a3 a4 status`, which pauses before each step (Enter runs it, `q` stops), or run one step at a time by name, e.g. `scripts/demo_skills_beat.sh a3`. Use one step at a time if the beats are interleaved with Hamza's.

## 4. The steps

Times are the talking budget. "Machine" is what the script took in rehearsal 2. The outputs are copied from rehearsal 2, with the home folder shown as `~` and hashes shortened.

### reset (before the stage; machine 0.9 s)

```text
$ cim skills corpus verify --root skills
corpus: manifest verifies
$ cim init cim.toml --db store.sqlite --origin demo-host --skill-root skills
init: wrote cim.toml (store store.sqlite, origin demo-host, 1 skill root(s))
  OK   fresh workspace; the copy matches the pinned corpus
```

It also stops any `cim watch`, dashboard or listener this script started earlier for the same workspace. The A3 notes and the A4 update are copied to `<work>/attacks/`, outside the watched skill root, like any user file.

### inventory: C1 (40 s; machine 0.7 s)

```text
$ cim inventory
inventory: skills=15 new_baselines=15 chain=ok
$ cim skills board --db store.sqlite
skills: 15 installed, 0 warning, 15 learning, 0 healthy; 0 file changes, 0 runs, 0 alerts
archive-pack: learning | files unchanged | behaviour no runs (0/30)
...
dashboard: http://127.0.0.1:8766  (Skills panel)
  OK   dashboard Skills panel lists all 15 skills
```

**Say:** every installed skill is now in the append-only store with a hash of each file and of the whole tree. None has run yet, so each is "learning, 0 of 30", never "healthy". **Show:** the browser on the dashboard's Skills panel.

### watch (10 s; machine 1.0 s)

```text
$ cim watch &
$ cim status
collectors cim watch running since … · skills-watcher running (0 restarts)
inventory  mcp: 0 servers, 0 tools   skills: 15
findings   0 changed artefacts
  OK   cim watch running, skills watcher running
```

**Say:** the monitor runs as a supervisor; if the watcher dies it is restarted, and the restart is recorded.

### warmup: C2-style capture (40 s; machine 16.8 s)

```text
$ cim skills exec --db store.sqlite --root skills meeting-brief -- scripts/brief.py notes.md   (x30)
  warm-up meeting-brief: 10/30 runs … 30/30 runs
$ cim skills exec --db store.sqlite --root skills word-count -- scripts/count.py sample.txt   (x30)
  warm-up word-count: 10/30 runs … 30/30 runs
skills: 15 installed, 0 warning, 13 learning, 2 healthy; 0 file changes, 60 runs, 0 alerts
meeting-brief: healthy | files unchanged | behaviour warmed up
word-count: healthy | files unchanged | behaviour warmed up
  OK   meeting-brief and word-count warmed up, no alert
```

**Say:** an agent harness calls `cim skills exec` instead of running the helper itself. Each run happens in its own cgroup scope under `strace`, and what it executed, wrote and connected to is recorded. This is 30 runs sped up. **Show:** the dashboard, where the two skills turn healthy.

### tamper: integrity (25 s; machine 0.5 s)

```text
$ echo '# demo tamper: this line was added after the baseline' >> skills/markdown-toc/scripts/toc.py
$ cim events --kind integrity --last 1
#76 2026-11-27T18:03:47Z skills  integrity markdown-toc: modify scripts/toc.py
  OK   the watcher recorded the edit (within 1 s)
```

**Say:** any change to an installed skill's files is recorded at once, through file notifications backed by a periodic sweep.

### a3: C4, skills side (60 s; machine 1.5 s)

```text
$ grep -n -i quarterly …/attacks/t17-a3-trigger/notes-quarterly.md
1:# Quarterly planning
5:- Draft the quarterly report outline

file hashes of meeting-brief, before the run:
2bc8767f4b04b093…  ./decoy/brief-token.txt
0f61c38efdd817ec…  ./notes.md
b517456651f474ca…  ./scripts/brief.py
b70c9cabf6c93707…  ./SKILL.md

$ cim skills exec --db store.sqlite --root skills -v meeting-brief -- scripts/brief.py …/notes-quarterly.md --host 127.0.0.1 --port 43333
brief: 3 action points
- Draft the quarterly report outline
- Collect the numbers from each work package
- Share the outline before Friday
exec: behaviour alert: meeting-brief changed how it behaves: destinations never seen: private_ip:43333
exec: recorded meeting-brief inv-f766d73dbab1 exit=0 processes=1: egress private_ip:43333

file hashes of meeting-brief, after the run:   (the same four lines)
  OK   file hashes identical before and after
$ cim events --kind alert --last 1
#78 … skills  alert     meeting-brief: meeting-brief changed how it behaves: destinations never seen: private_ip:43333
what the local listener received (variable NAMES and the decoy, never values):
{"env_names": ["HOME", "LANG", "PATH", "PWD", "PYTHONDONTWRITEBYTECODE", "SHLVL"], "decoy": "CIM-LAB-DECOY: this file is fake and holds nothing of value.\n"}
  OK   the store has no file change for meeting-brief (integrity: unchanged)
```

**Say:** the skill has not changed, as the hashes show. Its input contains the trigger word, and it does something it never did in 30 runs: it connects out. The scorer (T-16) names the drifted feature, a destination never seen. The output the agent gets looks normal. **Show:** the dashboard, where `meeting-brief` turns to warning with 1 alert and its files stay unchanged.

Without `--listener`, the script starts a one-shot listener on 127.0.0.1 on a free port, so the port changes on every run. On VM-MON it is the lab listener (section 7).

### a4: false-positive control (30 s; machine 1.2 s)

```text
$ diff -u skills/word-count/scripts/count.py attacks/t17-a4-update/word-count/scripts/count.py
+… and the longest line (v2)
+longest = max((len(line) for line in lines), default=0)
$ cp -r attacks/t17-a4-update/word-count/. skills/word-count/
$ cim events --kind integrity --last 2
#79 … skills  integrity word-count: modify SKILL.md
#80 … skills  integrity word-count: modify scripts/count.py
$ cim skills exec --db store.sqlite --root skills -v word-count -- scripts/count.py sample.txt
lines=3 words=13 chars=67 longest=24
exec: recorded word-count inv-fdc7d2c206b3 exit=0 processes=1: nothing
  OK   no behaviour alert after the update
```

**Say:** a real update is a file change, and it is recorded as one. Its behaviour is the same as before, so the scorer stays silent. Accepting an update as the new baseline is FYP II (T-31).

### status: C5 (35 s; machine 0.8 s)

```text
$ cim status
store      ~/.cache/cim-demo/skills-beat/store.sqlite   chain ok   81 records   tip e44f…fa   hash v2
collectors cim watch running since 2026-11-27T18:03:29Z · skills-watcher running (0 restarts)
inventory  mcp: 0 servers, 0 tools   skills: 15
findings   2 changed artefacts:
           skill markdown-toc (modify scripts/toc.py, 18:03:47)
           skill word-count (modify SKILL.md; modify scripts/count.py, 18:03:49)
           1 behaviour alert   0 monitor events   0 capture faults
learning   mcp: 0 tools under 30 calls   skills: 13 under 30 runs
  exit 1 (1 = something was found; 2 = the monitor is not running)
$ cim events --side skills --kind alert --kind integrity --last 10
  (the tamper, the A3 alert, the two A4 changes)
  OK   dashboard Skills panel: meeting-brief and the two changed skills in warning
$ cim verify-chain
verify-chain: ok (81 records) tip=e44f39455c38…
```

**Say:** one summary of what is installed, what changed and what behaved differently. The store is hash-chained, and the chain verifies.

### stop (after Q&A)

`scripts/demo_skills_beat.sh stop` stops `cim watch`, the dashboard and the listener. A later `cim status` on the workspace exits 2 (monitor not running), as it should.

## 5. Rehearsals

All four on 2026-11-27, with the script from this PR, in the default workspace. Two ran on Fasih's laptop (Fedora 44) and two on VM-MON, as the operator `cim`, with CIM at `332c6e9` and `--listener 10.10.10.30:9000 --origin vm-mon`.

| | Where | Started (UTC) | Mode | Checks | Machine time per step (s) | Total |
|---|---|---|---|---|---|---|
| 1 | laptop | 18:02:56 | `--no-pause`, from no workspace | 17 / 17 OK | reset 0.4 · inventory 0.7 · watch 0.9 · warmup 16.6 · tamper 0.5 · a3 1.6 · a4 1.2 · status 0.8 | 23 s |
| 2 | laptop | 18:03:27 | paused before each step (Enter fed in), reset over rehearsal 1's live workspace | 17 / 17 OK | reset 0.9 · inventory 0.7 · watch 1.0 · warmup 16.8 · tamper 0.5 · a3 1.5 · a4 1.2 · status 0.8 | 23 s |
| 3 | VM-MON | 18:26:40 | `--no-pause`, from no workspace | 16 / 16 OK | reset 0.4 · inventory 0.8 · watch 1.0 · warmup 17.9 · tamper 0.6 · a3 1.4 · a4 1.3 · status 0.9 | 25 s |
| 4 | VM-MON | 18:27:21 | paused (Enter fed in), reset over rehearsal 3's live workspace | 16 / 16 OK | reset 0.9 · inventory 0.8 · watch 0.9 · warmup 18.0 · tamper 0.7 · a3 1.4 · a4 1.3 · status 0.9 | 25 s |

- After each run, `stop` left no process behind, and nothing changed under `corpora/` (laptop: `git status`; VM-MON: the corpus is the clone's).
- On VM-MON there is one check fewer: with `--listener`, the script does not run the local listener check. Instead, the lab listener's log was checked after each A3. Each run added one line, from `10.10.10.10`, port 9000, 148 bytes, preview `{"env_names": ["HOME", "LANG", "PATH", "PWD", "PYTHONDONTWRITEBYTECODE"], "decoy": "CIM-LAB-DECOY: …"}`. The alert read `destinations never seen: private_ip:9000`.
- The listener's timestamps were about 6 s later than VM-MON's alert time for the same run. The two VMs' clocks differ slightly; nothing reads them together.
- The dashboard on VM-MON was opened from the laptop through the SSH tunnel in section 7: page 200, and the Skills panel data showed the 3 skills in warning and 1 alert.
- The operator's own store and `cim watch` on VM-MON were not touched by the demo: 169 records and the same chain tip before and after.

**Broken in the first trial run, fixed before the rehearsals:**
- **`cim skills exec` lost the `--` separator** (a real bug, not specific to the demo). Click drops the first `--` from a command's arguments, so `cim skills exec … meeting-brief -- scripts/brief.py notes --host H --port P` failed with "unrecognized arguments: --host". `python -m cim.skills exec` was fine. Any agent harness passing a flag to a helper through `cim skills exec` would have hit this. Fixed in `src/cim/skills/cli.py`, which now hands on the arguments exactly as typed. Two tests in `tests/skills/test_skills_exec.py`, both failing without the fix.
- `exec --help` still said "No score is computed"; it has been scoring since PR #46. The text is corrected.
- Script fixes: an integrity wait that counted all records, so a re-run could pass with a dead watcher (it now waits for new ones); a dashboard wait with no timeout (34 s hang on a taken port); and a re-run of `inventory` failing on `new_baselines=0`.

## 6. What was not rehearsed

- **HexStrike and Hamza's MCP beats**, and the hand-overs between them and these steps.
- **The two-store question** (section 2) and a dashboard showing both sides.
- **A lab listener that is down.** Only a refused connection on the laptop was tried (the row in section 8).
- **A projector, the browser view and narration timing.** The talking budgets are estimates. Only the machine times were measured.
- **The backup video (C6).** Not recorded.

## 7. On VM-MON (rehearsed 3 and 4)

1. **CIM on VM-MON must have this PR** (the `cim skills` fix). Since 2026-11-27 it is at `332c6e9`, snapshot `cim-332c6e9` (updated, isolated, before any demo run). To update it again, follow "Update CIM" in `docs/setup/vm-mon.md`.
2. From the laptop, a shell as the operator: `scripts/lab/vm_mon.sh ssh cim`. Then, in `~/cim`:

   ```bash
   scripts/demo_skills_beat.sh --listener 10.10.10.30:9000 --origin vm-mon reset
   scripts/demo_skills_beat.sh --listener 10.10.10.30:9000 --origin vm-mon inventory watch warmup tamper a3 a4 status
   ```

3. The dashboard listens on VM-MON's 127.0.0.1:8766. To view it on the laptop, open a second terminal and run:

   ```bash
   ssh -i ~/.ssh/cim_lab_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=~/.cache/cim-lab/known_hosts \
     -N -L 8766:127.0.0.1:8766 cim@10.10.10.10
   ```

   Then browse to <http://127.0.0.1:8766> on the laptop. The tunnel needs the dashboard to be running, so open it after `inventory`.
4. After `a3`, show what the lab listener logged: `scripts/lab/lab.sh listener ssh labadmin 'sudo tail -1 /var/log/cim-listener/connections.jsonl'`.
5. The demo store (`~cim/.cache/cim-demo/skills-beat/store.sqlite`) is separate from the operator's store (`~cim/cim-data/cim-store.sqlite`, watched by the `cim-watch` unit), so the two do not mix.
6. After the demo, `snapshot-revert vm-mon cim-332c6e9` gives a clean VM again (`docs/setup/vm-mon.md`).

## 8. What can go wrong on stage

"Tested" means the failure was caused on purpose and the recovery run, on 2026-11-27.

| What goes wrong | How it shows | Recovery | Tested |
|---|---|---|---|
| Dashboard port already taken | `FAIL the dashboard did not start (port 8766 taken?)` and `Address already in use` | `scripts/demo_skills_beat.sh --dashboard-port 8767 inventory` (re-running `inventory` is safe: it baselines nothing twice) | yes |
| The skills watcher dies (crash, `kill -9`) | `cim status`: `skills-watcher running (1 restart)`; event `collector_restarted (exited)` | Nothing to do: `cim watch` restarts it within about 2 s and records it. Point at it: that is the T-13 watchdog working. The next tamper is still caught | yes |
| `cim watch` itself is not running | `tamper` or `a4`: `FAIL no integrity event … within 10 s (is cim watch running?)`; `status`: exit 2, `cim watch NOT RUNNING` | `scripts/demo_skills_beat.sh watch`, then the failed step again | yes |
| Warm-up skipped, failed or too short | `a3`: `FAIL one new behaviour alert` while the board says `learning N/30` (the scorer stays silent during warm-up, by design) | `scripts/demo_skills_beat.sh warmup` (adds 30 runs), then `a3` | yes (`--warmup 5`) |
| A3 has to be run again | A second alert | Fine: a retry alerts each time, including to the same fixed destination (3 of 3 to `127.0.0.1:9`), and `status` accepts one or more alerts | yes |
| A4 run twice | `FAIL the update was not recorded … already applied?` | Say so: the update is already in. For a clean screen, `reset` and run the steps again (about 25 s) | yes |
| Lab listener down or unreachable | A3 still alerts (the connection attempt is what is recorded), but the listener log is empty | Carry on; mention it. The alert does not depend on the listener. Check with `scripts/lab/lab.sh listener ssh labadmin 'systemctl is-active cim-listener'` | refused connection on the laptop yes; a stopped lab listener no |
| Dashboard tunnel to VM-MON fails (`bind: Address already in use`) | Nothing at <http://127.0.0.1:8766> on the laptop | A laptop dashboard or old tunnel holds 8766: stop it, or tunnel `-L 8767:127.0.0.1:8766` and browse to 8767 | no |
| No systemd user session or no strace (e.g. after `su`, or ssh without lingering) | `warmup` fails at run 1; exec says it needs a systemd user session or strace (exit 125). The helper does not run untraced | Log in as the operator directly (ssh as `cim`, which lingers on VM-MON), check `systemctl --user is-system-running`, then `reset` and go again | unit test only (`test_without_scope_or_tracer_it_stops_and_never_runs_untraced`) |
| Left-over processes from a rehearsal | A second `cim watch` refused, or a stale dashboard | `reset` stops what this script started for the workspace | yes |
| Long paths wrap on the projector | Hard-to-read command lines | Use `--work ~/demo` on every call | no |
| Anything else that cannot be fixed in 30 s | | Switch to the backup video (C6) | **no video yet** |
