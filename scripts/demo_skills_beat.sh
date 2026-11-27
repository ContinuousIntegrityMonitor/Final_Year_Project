#!/usr/bin/env bash
# T-18: the skills part of the December demo, step by step (runbook: docs/demo/T18_skills_beat.md).
#
# Works on a COPY of the seed corpus in a workspace of its own, the way `cim skills attack`
# does. It never writes under corpora/skills: the corpus is only read, by `cp` in `reset`.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STEPS=(reset inventory watch warmup tamper a3 a4 status)
MARKER=".cim-demo-skills-beat"

usage() {
  cat <<'EOF'
Usage: scripts/demo_skills_beat.sh [options] [STEP ...]

The skills part of the December demo (T-18). Runbook: docs/demo/T18_skills_beat.md.

Steps, in demo order (no STEP, or "all", runs them all and pauses before each one):
  reset      stop anything left from a previous run; fresh workspace: corpus copy,
             cim.toml, empty store
  inventory  cim inventory: baseline every installed skill (C1); start the dashboard
             and check its Skills panel lists them all
  watch      start cim watch (the skills watcher under its supervisor)
  warmup     the warm-up, sped up: 30 traced runs each of meeting-brief and word-count
             through cim skills exec, the way an agent harness calls them
  tamper     edit one installed helper; the watcher records it (integrity, T-10)
  a3         T-17 A3: meeting-brief on notes that mention "quarterly"; the behaviour alert
             names the never-seen destination, and the skill's file hashes are shown
             unchanged before and after (C4, skills side)
  a4         T-17 A4: a legitimate update of word-count; recorded as file changes, and
             the next run raises no behaviour alert (false-positive control)
  status     cim status, the alert and integrity events, cim verify-chain (C5)
  stop       stop cim watch, the dashboard and the listener (not part of "all", so the
             dashboard stays up for Q&A)

Every step checks its own result and prints OK or FAIL; the exit status is 1 if any check
failed. Each step's time goes to <work>/timings.tsv.

Options:
  --work DIR            workspace (default: $CIM_DEMO_WORK, else ~/.cache/cim-demo/skills-beat).
                        reset deletes it, so it must be empty, missing, or a workspace this
                        script made
  --corpus DIR          corpus to copy (default: <repo>/corpora/skills); only read
  --listener HOST:PORT  where A3 sends (on VM-MON: 10.10.10.30:9000, the lab listener);
                        default: a one-shot listener on 127.0.0.1 that this script starts
  --dashboard-port N    dashboard port (default: 8766; Hamza's MCP beats keep 8765)
  --origin NAME         host name recorded with each artefact (default: the short host
                        name, or demo-host when that is an address)
  --warmup N            warm-up runs per skill (default: 30, the scorer's warm-up; with
                        fewer, the scorer stays silent and A3 shows no alert)
  --no-pause            do not wait for Enter between steps (rehearsals)
  -h, --help            this text

Environment: CIM_PYTHON, the Python that has cim installed (default: <repo>/.venv/bin/python,
else `uv run`). Needs a systemd user session and strace, as cim skills exec does.
EOF
}

WORK="${CIM_DEMO_WORK:-$HOME/.cache/cim-demo/skills-beat}"
CORPUS="$REPO/corpora/skills"
LISTENER=""
DASH_PORT=8766
WARMUP=30
ORIGIN="$(hostname -s 2>/dev/null || true)"
[[ "$ORIGIN" =~ ^[A-Za-z][A-Za-z0-9-]*$ ]] || ORIGIN=demo-host
PAUSE=1
WANTED=()
while (($#)); do
  case "$1" in
    -h | --help) usage; exit 0 ;;
    --work) WORK="$2"; shift 2 ;;
    --corpus) CORPUS="$2"; shift 2 ;;
    --listener) LISTENER="$2"; shift 2 ;;
    --dashboard-port) DASH_PORT="$2"; shift 2 ;;
    --warmup) WARMUP="$2"; shift 2 ;;
    --origin) ORIGIN="$2"; shift 2 ;;
    --no-pause) PAUSE=0; shift ;;
    all) WANTED+=("${STEPS[@]}"); shift ;;
    reset | inventory | watch | warmup | tamper | a3 | a4 | status | stop) WANTED+=("$1"); shift ;;
    *) echo "demo: unknown argument: $1 (see --help)" >&2; exit 2 ;;
  esac
done
if ((${#WANTED[@]} == 0)); then
  WANTED=("${STEPS[@]}")
fi
if [[ -n "$LISTENER" && ! "$LISTENER" =~ ^[^:]+:[0-9]+$ ]]; then
  echo "demo: --listener must be HOST:PORT" >&2
  exit 2
fi
[[ "$WARMUP" =~ ^[0-9]+$ ]] || { echo "demo: --warmup must be a number" >&2; exit 2; }

if [[ -n "${CIM_PYTHON:-}" ]]; then
  PY=("$CIM_PYTHON")
elif [[ -x "$REPO/.venv/bin/python" ]]; then
  PY=("$REPO/.venv/bin/python")
else
  PY=(uv run --project "$REPO" --quiet python)
fi

WORK="$(realpath -m "$WORK")"
CORPUS="$(realpath -m "$CORPUS")"
RUN="$WORK/run"  # pid files and logs of what this script started
export CIM_CONFIG="$WORK/cim.toml"

# What the audience sees: `cim ...` and `cim skills ...`, run with the right Python.
cim() { "${PY[@]}" -m cim "$@"; }
py() { "${PY[@]}" "$@"; }

BOLD=$'\e[1m' GREEN=$'\e[32m' RED=$'\e[31m' DIM=$'\e[2m' OFF=$'\e[0m'
if [[ ! -t 1 ]]; then BOLD="" GREEN="" RED="" DIM="" OFF=""; fi

FAILED=0
STEP_FAILED=0
say() { printf '\n%s$ %s%s\n' "$BOLD" "$*" "$OFF"; }  # print a command line, run nothing
show() { say "$@"; "$@"; }
note() { printf '%s  %s%s\n' "$DIM" "$*" "$OFF"; }
ok() { printf '%s  OK%s   %s\n' "$GREEN" "$OFF" "$*"; }
fail() { printf '%s  FAIL%s %s\n' "$RED" "$OFF" "$*"; STEP_FAILED=1; }
check() { # check "what" command...: OK when the command succeeds
  local what="$1"
  shift
  if "$@"; then ok "$what"; else fail "$what"; fi
}
die() { echo "demo: $*" >&2; exit 2; }

need_workspace() {
  [[ -f "$WORK/$MARKER" && -f "$WORK/store.sqlite" ]] ||
    die "no demo workspace with a store at $WORK: run the reset and inventory steps first"
}

alerts_now() { # skills behaviour alerts in the store
  cim status --json 2>/dev/null | py -c 'import json,sys; print(json.load(sys.stdin)["behaviour_alerts"]["skills"])' || true
}

integrity_count() { # integrity records for one skill
  cim events --kind integrity --side skills --last 0 2>/dev/null | grep -c " $1: " || true
}

wait_for_integrity() { # wait_for_integrity SKILL BEFORE NEW SECONDS: NEW records past BEFORE
  local skill="$1" want=$(($2 + $3)) deadline=$((SECONDS + $4))
  while ((SECONDS < deadline)); do
    (($(integrity_count "$skill") >= want)) && return 0
    sleep 0.25
  done
  return 1
}

hashes() { # the skill's files, as sha256sum lists them (relative paths, sorted)
  (cd "$WORK/skills/$1" && find . -type f -print0 | sort -z | xargs -0 sha256sum)
}

started_by_us() { # started_by_us PIDFILE: the pid is alive and is ours (its command names $WORK)
  local pid
  [[ -f "$1" ]] || return 1
  pid="$(cat "$1")"
  [[ -r "/proc/$pid/cmdline" ]] && tr '\0' ' ' <"/proc/$pid/cmdline" | grep -qF -- "$WORK"
}

stop_pidfile() {
  local file="$1" pid i
  if started_by_us "$file"; then
    pid="$(cat "$file")"
    kill -TERM "$pid" 2>/dev/null || true
    for ((i = 0; i < 40; i++)); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
    kill -KILL "$pid" 2>/dev/null || true
    note "stopped $(basename "$file" .pid) (pid $pid)"
  fi
  rm -f "$file"
}

start_bg() { # start_bg NAME command...: detached, survives this script; pid in run/NAME.pid
  local name="$1"
  shift
  mkdir -p "$RUN"
  setsid "$@" >"$RUN/$name.log" 2>&1 </dev/null &
  echo $! >"$RUN/$name.pid"
}

# ---------------------------------------------------------------------------- steps

step_stop() {
  [[ -d "$RUN" ]] || { note "nothing running for $WORK"; return 0; }
  stop_pidfile "$RUN/watch.pid"
  stop_pidfile "$RUN/dashboard.pid"
  stop_pidfile "$RUN/listener.pid"
}

step_reset() {
  case "$WORK" in
    / | "$HOME" | "$REPO" | "$REPO"/*) die "refusing to use $WORK as the workspace" ;;
  esac
  [[ "$CORPUS" == "$WORK" || "$CORPUS" == "$WORK"/* ]] && die "the corpus is inside $WORK"
  [[ "$WORK" == "$CORPUS"/* ]] && die "$WORK is inside the corpus"
  [[ -f "$CORPUS/MANIFEST.json" ]] || die "no corpus at $CORPUS (MANIFEST.json missing)"
  if [[ -d "$WORK" && -n "$(ls -A "$WORK")" && ! -f "$WORK/$MARKER" ]]; then
    die "$WORK is not empty and was not made by this script; pick another --work"
  fi
  step_stop
  rm -rf "$WORK"
  mkdir -p "$WORK"
  touch "$WORK/$MARKER"
  cd "$WORK"
  # The copy: skills under skills/, the attack material (A3 notes, A4 update) beside it,
  # outside the watched root, like any user file.
  cp -r "$CORPUS" skills
  mv skills/_attacks attacks
  note "corpus copied from $CORPUS to $WORK/skills (the corpus itself is only read)"
  local out
  out="$(show cim skills corpus verify --root skills)"
  echo "$out"
  show cim init cim.toml --db store.sqlite --origin "$ORIGIN" --skill-root skills
  check "fresh workspace; the copy matches the pinned corpus" grep -q "manifest verifies" <<<"$out"
}

step_inventory() {
  [[ -f "$WORK/$MARKER" ]] || die "no demo workspace at $WORK: run the reset step first"
  local out board
  out="$(show cim inventory)"
  echo "$out"
  check "15 skills baselined, chain ok" grep -qE "skills=15 new_baselines=[0-9]+ chain=ok" <<<"$out"
  show cim skills board --db store.sqlite | sed -n '1,6p'
  note "... (one line per skill)"
  stop_pidfile "$RUN/dashboard.pid"
  start_bg dashboard "${PY[@]}" -m cim dashboard --db "$WORK/store.sqlite" --port "$DASH_PORT"
  local i
  for ((i = 0; i < 40; i++)); do
    board="$(curl -s -m 2 "http://127.0.0.1:$DASH_PORT/api/board" 2>/dev/null || true)"
    [[ -n "$board" ]] && break
    started_by_us "$RUN/dashboard.pid" || break  # it exited: the port is taken, most likely
    sleep 0.25
  done
  if ! started_by_us "$RUN/dashboard.pid"; then
    tail -1 "$RUN/dashboard.log"
    fail "the dashboard did not start (port $DASH_PORT taken?): rerun with --dashboard-port N inventory"
  fi
  printf '\n%sdashboard: http://127.0.0.1:%s  (Skills panel)%s\n' "$BOLD" "$DASH_PORT" "$OFF"
  check "dashboard Skills panel lists all 15 skills" py -c '
import json, sys
board = json.loads(sys.argv[1])
summary = board["skills"]["summary"]
print("  /api/board skills summary:", summary)
sys.exit(0 if summary["skills"] == 15 else 1)
' "${board:-null}" 2>/dev/null
}

step_watch() {
  need_workspace
  stop_pidfile "$RUN/watch.pid"
  start_bg watch "${PY[@]}" -m cim watch --config "$WORK/cim.toml"
  printf '\n%s$ cim watch &%s   %s(runs in the background; log: run/watch.log)%s\n' \
    "$BOLD" "$OFF" "$DIM" "$OFF"
  local i
  for ((i = 0; i < 40; i++)); do
    grep -q "started skills-watcher" "$RUN/watch.log" 2>/dev/null && break
    sleep 0.25
  done
  sleep 0.5  # the watcher takes its first sweep
  local out
  out="$(show cim status || true)"
  echo "$out"
  check "cim watch running, skills watcher running" grep -q "skills-watcher running" <<<"$out"
}

warm() { # warm SKILL SCRIPT ARGS...: WARMUP traced runs through cim skills exec
  local skill="$1" i
  shift
  printf '\n%s$ cim skills exec --db store.sqlite --root skills %s -- %s%s   %s(x%s)%s\n' \
    "$BOLD" "$skill" "$*" "$OFF" "$DIM" "$WARMUP" "$OFF"
  for ((i = 1; i <= WARMUP; i++)); do
    cim skills exec --db store.sqlite --root skills "$skill" -- "$@" >/dev/null 2>"$RUN/exec.err" ||
      { cat "$RUN/exec.err"; fail "$skill run $i failed"; return 0; }
    if ((i % 10 == 0 || i == WARMUP)); then printf '  warm-up %s: %d/%d runs\n' "$skill" "$i" "$WARMUP"; fi
  done
}

step_warmup() {
  need_workspace
  cd "$WORK"
  mkdir -p "$RUN"
  warm meeting-brief scripts/brief.py notes.md
  warm word-count scripts/count.py sample.txt
  local out
  out="$(show cim skills board --db store.sqlite)"
  grep -E "^skills:|meeting-brief|word-count" <<<"$out"
  if ((WARMUP >= 30)); then
    check "meeting-brief and word-count warmed up, no alert" \
      test "$(grep -cE '^(meeting-brief|word-count): .*warmed up$' <<<"$out")" = 2
  else
    note "--warmup $WARMUP is under the scorer's 30: the board still says learning"
  fi
}

step_tamper() {
  need_workspace
  cd "$WORK"
  local line="# demo tamper: this line was added after the baseline" before
  before="$(integrity_count markdown-toc)"
  say "echo '$line' >> skills/markdown-toc/scripts/toc.py"
  echo "$line" >>skills/markdown-toc/scripts/toc.py
  local start=$SECONDS
  if wait_for_integrity markdown-toc "$before" 1 10; then
    show cim events --kind integrity --last 1
    ok "the watcher recorded the edit (within $((SECONDS - start + 1)) s)"
  else
    fail "no integrity event for markdown-toc within 10 s (is cim watch running?)"
  fi
}

step_a3() {
  need_workspace
  cd "$WORK"
  local notes="$WORK/attacks/t17-a3-trigger/notes-quarterly.md" host port before after
  local alerts_before
  alerts_before="$(alerts_now)"
  note "the trigger input is a user's notes file, outside the skill; it mentions \"quarterly\":"
  show grep -n -i quarterly "$notes"
  printf '\n%sfile hashes of meeting-brief, before the run:%s\n' "$BOLD" "$OFF"
  before="$(hashes meeting-brief)"
  sed -E 's/^(.{16})[0-9a-f]+/\1…/' <<<"$before"
  if [[ -n "$LISTENER" ]]; then
    host="${LISTENER%:*}" port="${LISTENER##*:}"
    note "A3 sends to the lab listener $LISTENER (check its log on the listener VM)"
  else
    host=127.0.0.1
    port="$(py -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
    rm -f "$RUN/listener.bin"
    start_bg listener "${PY[@]}" -c '
import socket, sys
server = socket.create_server(("127.0.0.1", int(sys.argv[1]))); server.settimeout(60)
connection, _ = server.accept(); connection.settimeout(5); data = b""
while chunk := connection.recv(65536):
    data += chunk
open(sys.argv[2], "wb").write(data)
' "$port" "$RUN/listener.bin" "$WORK"
    sleep 0.3
  fi
  show cim skills exec --db store.sqlite --root skills -v meeting-brief -- \
    scripts/brief.py "$notes" --host "$host" --port "$port" || true
  printf '\n%sfile hashes of meeting-brief, after the run:%s\n' "$BOLD" "$OFF"
  after="$(hashes meeting-brief)"
  sed -E 's/^(.{16})[0-9a-f]+/\1…/' <<<"$after"
  check "file hashes identical before and after" test "$before" = "$after"
  show cim events --kind alert --last 1
  check "one new behaviour alert" test "$(alerts_now)" -gt "$alerts_before"
  check "the alert names the never-seen destination" \
    grep -q "destinations never seen" <<<"$(cim events --kind alert --last 1)"
  if [[ -z "$LISTENER" ]]; then
    local i
    for ((i = 0; i < 20; i++)); do [[ -s "$RUN/listener.bin" ]] && break; sleep 0.25; done
    printf '\n%swhat the local listener received (variable NAMES and the decoy, never values):%s\n' \
      "$BOLD" "$OFF"
    cat "$RUN/listener.bin" 2>/dev/null && echo
    check "the listener received the A3 payload" grep -q '"env_names"' "$RUN/listener.bin"
  fi
  local integrity
  integrity="$(cim skills board --db store.sqlite --json | py -c '
import json, sys
skill = next(s for s in json.load(sys.stdin)["skills"] if s["skill_id"] == "meeting-brief")
print(skill["integrity"]["state"])')"
  check "the store has no file change for meeting-brief (integrity: $integrity)" test "$integrity" = unchanged
}

step_a4() {
  need_workspace
  cd "$WORK"
  local update="attacks/t17-a4-update/word-count" alerts_before before
  alerts_before="$(alerts_now)"
  before="$(integrity_count word-count)"
  note "a legitimate update: count.py now also reports the longest line"
  say diff -u skills/word-count/scripts/count.py "$update/scripts/count.py"
  diff -u skills/word-count/scripts/count.py "$update/scripts/count.py" | sed -n '3,$p' | grep '^[+-]' || true
  show cp -r "$update/." skills/word-count/
  if wait_for_integrity word-count "$before" 2 10; then
    show cim events --kind integrity --last 2
    ok "the update recorded as two file changes"
  else
    fail "the update was not recorded within 10 s (is cim watch running? already applied?)"
  fi
  show cim skills exec --db store.sqlite --root skills -v word-count -- scripts/count.py sample.txt
  check "no behaviour alert after the update" test "$(alerts_now)" = "$alerts_before"
}

step_status() {
  need_workspace
  cd "$WORK"
  local rc=0
  show cim status || rc=$?
  note "exit $rc (1 = something was found; 2 = the monitor is not running)"
  check "cim status exit 1: findings present" test "$rc" = 1
  check "status: 2 changed skills, a skills behaviour alert, chain ok, watch running" py -c '
import json, subprocess, sys
s = json.loads(subprocess.run(sys.argv[1:] + ["-m", "cim", "status", "--json"],
                              capture_output=True, text=True).stdout)
names = sorted(f["artefact"] for f in s["findings"])
print("  findings:", names, "alerts:", s["behaviour_alerts"], "chain:", s["chain"]["reason"])
ok = (names == ["skill markdown-toc", "skill word-count"] and s["behaviour_alerts"]["skills"] >= 1
      and s["chain"]["ok"] and s["collectors"]["watch"]["running"])
sys.exit(0 if ok else 1)' "${PY[@]}"
  show cim events --side skills --kind alert --kind integrity --last 10
  if started_by_us "$RUN/dashboard.pid"; then
    check "dashboard Skills panel: meeting-brief and the two changed skills in warning" py -c '
import json, sys, urllib.request
board = json.load(urllib.request.urlopen(sys.argv[1], timeout=5))["skills"]
states = {s["skill_id"]: s["state"] for s in board["skills"]}
print("  /api/board skills summary:", board["summary"])
ok = all(states[k] == "warning" for k in ("meeting-brief", "markdown-toc", "word-count"))
sys.exit(0 if ok and board["summary"]["alerts"] >= 1 else 1)' "http://127.0.0.1:$DASH_PORT/api/board"
  else
    note "the dashboard is not running (inventory starts it)"
  fi
  local out
  rc=0
  out="$(show cim verify-chain)" || rc=$?
  echo "$out"
  check "verify-chain ok" test "$rc" = 0
}

# ---------------------------------------------------------------------------- driver

declare -A CRITERIA=(
  [reset]="setup" [inventory]="C1" [watch]="setup" [warmup]="C2-style capture"
  [tamper]="integrity" [a3]="C4 (skills)" [a4]="A4 control" [status]="C5" [stop]="teardown"
)
declare -A RESULTS=()
mkdir -p "$(dirname "$WORK")"
total_start=$SECONDS
first=1
for step in "${WANTED[@]}"; do
  if ((PAUSE && ${#WANTED[@]} > 1 && !first)); then
    read -r -p "${BOLD}next: $step (${CRITERIA[$step]}). Enter to run, q to stop: ${OFF}" answer || answer=q
    [[ "$answer" == q ]] && break
  fi
  first=0
  printf '\n%s== %s (%s) ==%s\n' "$BOLD" "$step" "${CRITERIA[$step]}" "$OFF"
  STEP_FAILED=0
  started=$(date +%s.%N)
  "step_$step" || STEP_FAILED=1  # a step reports FAIL; it does not stop the run
  took="$(py -c 'import sys; print(f"{float(sys.argv[2]) - float(sys.argv[1]):.1f}")' "$started" "$(date +%s.%N)")"
  result=$([[ $STEP_FAILED == 0 ]] && echo OK || echo FAIL)
  RESULTS[$step]="$result $took s"
  ((STEP_FAILED)) && FAILED=1
  note "$step: $result in $took s"
  if [[ -d "$WORK" ]]; then
    printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$step" "$took" "$result" >>"$WORK/timings.tsv"
  fi
done

if ((${#RESULTS[@]} > 1)); then
  printf '\n%ssummary (%d s in all)%s\n' "$BOLD" "$((SECONDS - total_start))" "$OFF"
  for step in "${WANTED[@]}"; do
    [[ -n "${RESULTS[$step]:-}" ]] && printf '  %-10s %-18s %s\n' "$step" "${CRITERIA[$step]}" "${RESULTS[$step]}"
  done
fi
exit "$FAILED"
