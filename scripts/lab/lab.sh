#!/usr/bin/env bash
# Build one CIM lab VM (T-04; corpora/mcp/topology.json) on a Linux host with KVM and libvirt.
# Runs as your user against qemu:///system; no sudo when polkit lets your user manage libvirt
# (add yourself to the libvirt group, or a desktop password prompt appears and times out).
#
#   scripts/lab/lab.sh <vm> all          # every step below, in order
#   scripts/lab/lab.sh <vm> <step>       # net pool key image create wait provision isolate
#                                        # check snapshot [name]
#   scripts/lab/lab.sh <vm> ssh [user] [command...]
#   scripts/lab/lab.sh <vm> run <user|root> <script>   # one of the VM's scripts, on the VM
#   scripts/lab/lab.sh <vm> destroy --yes   # the VM, its disks and its snapshots
#
# <vm> is a folder under scripts/lab/ (vm-mon, vm-tgt, listener) holding vm.env, domain.xml,
# the cloud-init files and the VM's own provisioning and check scripts. Each step is safe to
# re-run: it skips what already exists. Settings: CIM_REPO_REF (default main), CIM_LAB_IMAGE_URL.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
NAME="${1:-}"
STEP="${2:-}"
[ -n "$NAME" ] && [ -f "$HERE/$NAME/vm.env" ] || { sed -n '2,15p' "$0"; exit 2; }
DIR="$HERE/$NAME"
# shellcheck source=/dev/null
. "$DIR/vm.env"   # VM, VM_IP, LAB_MAC, NAT_MAC (empty: no internet card), DISK_GB, PROVISION, CHECK

VIRSH=(virsh --connect qemu:///system --quiet)
NET=cim-lab
POOL=cim-lab
POOL_DIR=/var/lib/libvirt/images/cim-lab
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/cim-lab"
KEY="$HOME/.ssh/cim_lab_ed25519"
IMAGE_URL="${CIM_LAB_IMAGE_URL:-https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img}"
IMAGE_NAME="$(basename "$IMAGE_URL")"
BASE_VOL="ubuntu-24.04-base.img"
export REPO_URL="https://github.com/ContinuousIntegrityMonitor/Final_Year_Project.git"
export REPO_REF="${CIM_REPO_REF:-main}"
HEXSTRIKE_URL="$(sed -n 's/^repo=//p' "$REPO/corpora/mcp/hexstrike.pin")"
HEXSTRIKE_SHA="$(sed -n 's/^sha=//p' "$REPO/corpora/mcp/hexstrike.pin")"
export HEXSTRIKE_URL HEXSTRIKE_SHA
SSH_OPTS=(-i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new
          -o UserKnownHostsFile="$CACHE/known_hosts" -o ConnectTimeout=5 -o BatchMode=yes)

say() { printf '%s: %s\n' "$VM" "$*" >&2; }
die() { say "$*"; exit 1; }
has_vol() { "${VIRSH[@]}" vol-info --pool "$POOL" "$1" >/dev/null 2>&1; }
on_vm() { local user="$1"; shift; ssh "${SSH_OPTS[@]}" "$user@$VM_IP" "$@"; }
# A script from the VM's folder, run on the VM as `user`, with the lab settings in its environment.
run_on_vm() {
  local user="$1" script="$2"
  local vars="REPO_URL='$REPO_URL' REPO_REF='$REPO_REF' HEXSTRIKE_URL='$HEXSTRIKE_URL' HEXSTRIKE_SHA='$HEXSTRIKE_SHA'"
  if [ "$user" = root ]; then
    on_vm labadmin "sudo env $vars bash -s" < "$DIR/$script"
  else
    on_vm "$user" "env $vars bash -s" < "$DIR/$script"
  fi
}

step_net() {
  if ! "${VIRSH[@]}" net-info "$NET" >/dev/null 2>&1; then
    "${VIRSH[@]}" net-define "$HERE/cim-lab-net.xml"
    say "defined network $NET (10.10.10.0/24, isolated)"
  fi
  "${VIRSH[@]}" net-autostart "$NET" >/dev/null
  if [ "$("${VIRSH[@]}" net-info "$NET" | awk '/^Active:/ {print $2}')" != yes ]; then
    "${VIRSH[@]}" net-start "$NET" >/dev/null
  fi
  "${VIRSH[@]}" net-dumpxml "$NET" | grep -q '<forward' && die "$NET has a <forward>: it must be isolated"
  say "network $NET up, no forward"
}

step_pool() {
  if ! "${VIRSH[@]}" pool-info "$POOL" >/dev/null 2>&1; then
    "${VIRSH[@]}" pool-define-as "$POOL" dir --target "$POOL_DIR" >/dev/null
    "${VIRSH[@]}" pool-build "$POOL" >/dev/null
    say "defined storage pool $POOL at $POOL_DIR"
  fi
  "${VIRSH[@]}" pool-autostart "$POOL" >/dev/null
  if [ "$("${VIRSH[@]}" pool-info "$POOL" | awk '/^State:/ {print $2}')" != running ]; then
    "${VIRSH[@]}" pool-start "$POOL" >/dev/null
  fi
  "${VIRSH[@]}" pool-refresh "$POOL" >/dev/null
  say "pool $POOL running"
}

step_key() {
  mkdir -p "$CACHE" "$(dirname "$KEY")"
  if [ ! -f "$KEY" ]; then
    ssh-keygen -q -t ed25519 -N '' -C "cim-lab" -f "$KEY"
    say "made the lab SSH key $KEY (lab use only)"
  fi
}

step_image() {
  mkdir -p "$CACHE"
  if has_vol "$BASE_VOL"; then
    say "base image $BASE_VOL already in the pool"
    return
  fi
  local sums="$CACHE/SHA256SUMS"
  curl -fsSL "$(dirname "$IMAGE_URL")/SHA256SUMS" -o "$sums"
  local want
  want="$(awk -v f="*$IMAGE_NAME" '$2 == f || $2 == substr(f, 2) {print $1}' "$sums")"
  [ -n "$want" ] || die "no checksum for $IMAGE_NAME in SHA256SUMS"
  if [ ! -f "$CACHE/$IMAGE_NAME" ] || [ "$(sha256sum "$CACHE/$IMAGE_NAME" | cut -d' ' -f1)" != "$want" ]; then
    say "downloading $IMAGE_URL"
    curl -fL --retry 3 -C - --progress-bar "$IMAGE_URL" -o "$CACHE/$IMAGE_NAME.part"  # resumes
    mv "$CACHE/$IMAGE_NAME.part" "$CACHE/$IMAGE_NAME"
  fi
  [ "$(sha256sum "$CACHE/$IMAGE_NAME" | cut -d' ' -f1)" = "$want" ] || die "checksum mismatch for $IMAGE_NAME"
  say "image sha256 $want ok"
  echo "$want  $IMAGE_URL" > "$CACHE/image.sha256"
  "${VIRSH[@]}" vol-create-as "$POOL" "$BASE_VOL" "$(stat -c %s "$CACHE/$IMAGE_NAME")" --format qcow2 >/dev/null
  "${VIRSH[@]}" vol-upload --pool "$POOL" "$BASE_VOL" "$CACHE/$IMAGE_NAME"
  say "uploaded the base image as $BASE_VOL"
}

step_create() {
  [ -f "$KEY.pub" ] || die "run the key step first"
  if "${VIRSH[@]}" dominfo "$VM" >/dev/null 2>&1; then
    say "$VM is already defined"
  else
    local seed_dir="$CACHE/seed-$VM" iso="$CACHE/$VM-seed.iso"
    rm -rf "$seed_dir" && mkdir -p "$seed_dir"
    sed "s|@LAB_KEY@|$(cat "$KEY.pub")|" "$DIR/user-data.yaml" > "$seed_dir/user-data"
    cp "$DIR/meta-data.yaml" "$seed_dir/meta-data"
    cp "$DIR/network-config.yaml" "$seed_dir/network-config"
    genisoimage -quiet -output "$iso" -volid cidata -joliet -rock \
      "$seed_dir/user-data" "$seed_dir/meta-data" "$seed_dir/network-config"
    has_vol "$VM-seed.iso" && "${VIRSH[@]}" vol-delete --pool "$POOL" "$VM-seed.iso"
    "${VIRSH[@]}" vol-create-as "$POOL" "$VM-seed.iso" "$(stat -c %s "$iso")" --format raw >/dev/null
    "${VIRSH[@]}" vol-upload --pool "$POOL" "$VM-seed.iso" "$iso"
    if ! has_vol "$VM.qcow2"; then
      "${VIRSH[@]}" vol-create-as "$POOL" "$VM.qcow2" "${DISK_GB}G" --format qcow2 \
        --backing-vol "$BASE_VOL" --backing-vol-format qcow2 >/dev/null
    fi
    "${VIRSH[@]}" define "$DIR/domain.xml" >/dev/null
    say "defined $VM"
  fi
  if [ "$("${VIRSH[@]}" domstate "$VM")" != running ]; then
    "${VIRSH[@]}" start "$VM" >/dev/null
    say "started $VM"
  fi
}

step_wait() {
  say "waiting for SSH on $VM_IP and for cloud-init to finish"
  local deadline=$((SECONDS + 900))
  until on_vm labadmin true 2>/dev/null; do
    [ $SECONDS -lt $deadline ] || die "no SSH on $VM_IP after 15 minutes"
    sleep 5
  done
  on_vm labadmin "cloud-init status --wait >/dev/null; cloud-init status --long | sed -n '1,2p'" || true
}

step_provision() {
  local item
  for item in $PROVISION; do
    say "provisioning: ${item%%:*} runs ${item#*:}"
    run_on_vm "${item%%:*}" "${item#*:}"
  done
}

step_isolate() {
  # The card can be in the running VM, in its saved definition, or both: the build has it in
  # both, a card attached later for an update (docs/setup/vm-mon.md) only in the running VM.
  if [ -n "${NAT_MAC:-}" ]; then
    if "${VIRSH[@]}" domiflist "$VM" | grep -qi "$NAT_MAC"; then
      "${VIRSH[@]}" detach-interface "$VM" user --mac "$NAT_MAC" --live
      say "removed the internet card ($NAT_MAC) from the running $VM"
    fi
    if "${VIRSH[@]}" domiflist "$VM" --inactive | grep -qi "$NAT_MAC"; then
      "${VIRSH[@]}" detach-interface "$VM" user --mac "$NAT_MAC" --config
      say "removed the internet card ($NAT_MAC) from $VM's saved definition"
    fi
  fi
  step_check
}

step_check() {
  say "checking isolation on $VM"
  local cards
  cards="$("${VIRSH[@]}" domiflist "$VM" | awk 'NF {print $3}' | sort -u | tr '\n' ' ')"
  [ "$cards" = "$NET " ] || die "$VM networks: $cards (want only $NET)"
  on_vm labadmin 'test -z "$(ip route show default)"' || die "$VM has a default route"
  if on_vm labadmin 'timeout 5 curl -fsS -o /dev/null https://github.com' 2>/dev/null; then
    die "$VM reached the internet"
  fi
  say "isolated: only $NET, no default route, no internet"
  local item
  for item in ${CHECK:-}; do
    run_on_vm "${item%%:*}" "${item#*:}"
  done
}

step_snapshot() {
  local name="${1:-base}"
  if "${VIRSH[@]}" snapshot-info "$VM" "$name" >/dev/null 2>&1; then
    say "snapshot $name exists"
    return
  fi
  "${VIRSH[@]}" snapshot-create-as "$VM" "$name" \
    --description "$VM $name, isolated; $(date -u +%FT%TZ)" >/dev/null
  say "snapshot $name taken"
}

step_destroy() {
  [ "${1:-}" = "--yes" ] || die "destroy removes $VM, its disks and its snapshots: pass --yes"
  "${VIRSH[@]}" destroy "$VM" 2>/dev/null || true
  for snap in $("${VIRSH[@]}" snapshot-list "$VM" --name 2>/dev/null); do
    "${VIRSH[@]}" snapshot-delete "$VM" "$snap" >/dev/null
  done
  "${VIRSH[@]}" undefine "$VM" 2>/dev/null || true
  for vol in "$VM.qcow2" "$VM-seed.iso"; do
    has_vol "$vol" && "${VIRSH[@]}" vol-delete --pool "$POOL" "$vol" >/dev/null
  done
  say "removed $VM (the lab network, the base image and the pool are kept)"
}

case "$STEP" in
  net) step_net ;;
  pool) step_pool ;;
  key) step_key ;;
  image) step_image ;;
  create) step_create ;;
  wait) step_wait ;;
  provision) step_provision ;;
  isolate) step_isolate ;;
  check) step_check ;;
  snapshot) step_snapshot "${3:-base}" ;;
  all) step_net; step_pool; step_key; step_image; step_create; step_wait; step_provision
       step_isolate; step_snapshot base ;;
  ssh) user="${3:-labadmin}"; shift 3 || shift $#; on_vm "$user" "$@" ;;
  run) [ -n "${4:-}" ] || die "run <user|root> <script>"; run_on_vm "$3" "$4" ;;
  destroy) step_destroy "${3:-}" ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
