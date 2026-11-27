#!/usr/bin/env bash
# Record the T-18 skills beat on VM-MON as a video (C6, skills half): the backup video.
#
#   scripts/demo/record_skills_beat.sh [--out FILE.mp4] [--keep DIR]
#   (default output: ~/Videos/cim/T18_skills_beat_backup.mp4; --keep keeps the raw recording)
#
# Runs the beat on VM-MON (docs/demo/T18_skills_beat.md, section 7) from this laptop and records
# the terminal in a pseudo-terminal (real timings, colours). Between steps it takes headless Firefox
# screenshots of VM-MON's dashboard through an SSH tunnel. scripts/demo/render_beat_video.py then
# turns the recording, the screenshots and caption cards into an MP4 (ffmpeg, H.264).
#
# Needs: the lab up (scripts/lab/check_lab.sh), CIM on VM-MON with the T-18 script, the lab SSH
# key, firefox, ffmpeg, uv. Uses the demo workspace ~cim/demo on VM-MON,
# which it resets; the operator's own store is not touched.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="$HOME/Videos/cim/T18_skills_beat_backup.mp4"  # never in the repo: no media in git
KEEP=""
while (($#)); do
  case "$1" in
    -h | --help) sed -n '2,14p' "$0"; exit 0 ;;
    --out) OUT="$2"; shift 2 ;;
    --keep) KEEP="$2"; shift 2 ;;
    --drive) shift; break ;;  # internal: the part that runs inside `script`
    *) echo "record: unknown argument $1" >&2; exit 2 ;;
  esac
done

VM=cim@10.10.10.10
PORT=8766
DEMO="cd ~/cim && TERM=xterm-256color scripts/demo_skills_beat.sh --work ~/demo --listener 10.10.10.30:9000 --origin vm-mon"
SSH=(ssh -q -i "$HOME/.ssh/cim_lab_ed25519" -o IdentitiesOnly=yes -o BatchMode=yes
     -o UserKnownHostsFile="$HOME/.cache/cim-lab/known_hosts" -o ConnectTimeout=5)

marker() { printf '\033]777;cim:%s\007' "$1"; }  # invisible; the renderer cuts the video here

shot() { # shot NAME: two screenshots of VM-MON's dashboard (top of page; whole page)
  local dir="$WORK/shots"
  mkdir -p "$dir"
  firefox --headless --no-remote --profile "$WORK/firefox" --window-size=1600,2600 \
    --screenshot "$dir/$1.png" "http://127.0.0.1:$PORT/" >/dev/null 2>&1
  curl -s -m 5 "http://127.0.0.1:$PORT/api/board" >"$dir/$1.json" || true  # for the captions
  marker "shot:$1"
}

drive() {
  local step
  marker start
  for step in inventory watch warmup tamper a3 a4 status; do
    clear
    marker "step:$step"
    printf '\033[1;36mcim@vm-mon:~/cim$\033[0m scripts/demo_skills_beat.sh %s\n' "$step"
    sleep 1
    "${SSH[@]}" -t "$VM" "$DEMO $step" || true
    if [[ "$step" == a3 ]]; then
      printf '\n\033[1;36mlabadmin@listener$\033[0m sudo tail -1 /var/log/cim-listener/connections.jsonl\n'
      "$REPO/scripts/lab/lab.sh" listener ssh labadmin \
        'sudo tail -1 /var/log/cim-listener/connections.jsonl' | fold -w 118
    fi
    sleep 1
    marker "end:$step"
    case "$step" in inventory | warmup | a3 | status) shot "$step" ;; esac
  done
  marker stop
}

if [[ "${1:-}" == run ]]; then
  WORK="$2"
  drive
  exit 0
fi

WORK="${KEEP:-$(mktemp -d)}"
mkdir -p "$WORK/firefox"
echo 'user_pref("browser.shell.checkDefaultBrowser", false);' >"$WORK/firefox/user.js"
echo "record: workspace $WORK" >&2

# Off camera: a fresh demo workspace on VM-MON, and the dashboard tunnel.
"${SSH[@]}" "$VM" "$DEMO --no-pause reset" >"$WORK/reset.log"
"${SSH[@]}" "$VM" "$DEMO stop" >/dev/null 2>&1 || true
"${SSH[@]}" -o ExitOnForwardFailure=yes -N -L "$PORT:127.0.0.1:$PORT" "$VM" &
TUNNEL=$!
trap 'kill $TUNNEL 2>/dev/null || true' EXIT
sleep 1

PY=(uv run --quiet --no-project --with pyte --with pillow python "$HERE/render_beat_video.py")
"${PY[@]}" record --work "$WORK" -- bash "$0" --drive run "$WORK" || true
"${SSH[@]}" "$VM" "$DEMO stop" >/dev/null 2>&1 || true

mkdir -p "$(dirname "$OUT")"
"${PY[@]}" render --work "$WORK" --out "$OUT"
echo "record: wrote $OUT" >&2
