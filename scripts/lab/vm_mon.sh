#!/usr/bin/env bash
# Build VM-MON, the CIM lab's monitored host (T-04; corpora/mcp/topology.json), on a Linux host
# with KVM and libvirt. Runs as your user against qemu:///system; nothing here needs sudo when
# polkit lets your user manage libvirt (Fedora: members of wheel or libvirt).
#
#   scripts/lab/vm_mon.sh all          # every step below, in order (about 15 minutes)
#   scripts/lab/vm_mon.sh <step>       # one step: net pool key image create wait provision
#                                      #           isolate check snapshot hexstrike
#   scripts/lab/vm_mon.sh ssh [cim|labadmin] [command...]
#   scripts/lab/vm_mon.sh destroy --yes   # removes the VM, its disks and the lab network
#
# Each step is safe to re-run: it skips what already exists.
# Settings (environment): CIM_REPO_REF (default main), CIM_LAB_IMAGE_URL.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
VIRSH=(virsh --connect qemu:///system --quiet)
VM=vm-mon
NET=cim-lab
POOL=cim-lab
POOL_DIR=/var/lib/libvirt/images/cim-lab
VM_IP=10.10.10.10
NAT_MAC=52:54:00:10:10:99
DISK_GB=40
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/cim-lab"
KEY="$HOME/.ssh/cim_lab_ed25519"
IMAGE_URL="${CIM_LAB_IMAGE_URL:-https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img}"
IMAGE_NAME="$(basename "$IMAGE_URL")"
BASE_VOL="ubuntu-24.04-base.img"
REPO_URL="https://github.com/ContinuousIntegrityMonitor/Final_Year_Project.git"
REPO_REF="${CIM_REPO_REF:-main}"
HEXSTRIKE_URL="$(sed -n 's/^repo=//p' "$REPO/corpora/mcp/hexstrike.pin")"
HEXSTRIKE_SHA="$(sed -n 's/^sha=//p' "$REPO/corpora/mcp/hexstrike.pin")"
SSH_OPTS=(-i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new
          -o UserKnownHostsFile="$CACHE/known_hosts" -o ConnectTimeout=5 -o BatchMode=yes)

say() { printf 'vm-mon: %s\n' "$*" >&2; }
die() { say "$*"; exit 1; }
has_vol() { "${VIRSH[@]}" vol-info --pool "$POOL" "$1" >/dev/null 2>&1; }
on_vm() { local user="$1"; shift; ssh "${SSH_OPTS[@]}" "$user@$VM_IP" "$@"; }

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
  if ! has_vol "$BASE_VOL"; then
    "${VIRSH[@]}" vol-create-as "$POOL" "$BASE_VOL" "$(stat -c %s "$CACHE/$IMAGE_NAME")" --format qcow2 >/dev/null
    "${VIRSH[@]}" vol-upload --pool "$POOL" "$BASE_VOL" "$CACHE/$IMAGE_NAME"
    say "uploaded the base image as $BASE_VOL"
  fi
}

step_create() {
  [ -f "$KEY.pub" ] || die "run the key step first"
  if "${VIRSH[@]}" dominfo "$VM" >/dev/null 2>&1; then
    say "$VM is already defined"
  else
    local seed_dir="$CACHE/seed"
    rm -rf "$seed_dir" && mkdir -p "$seed_dir"
    sed "s|@LAB_KEY@|$(cat "$KEY.pub")|" "$HERE/vm-mon/user-data.yaml" > "$seed_dir/user-data"
    cp "$HERE/vm-mon/meta-data.yaml" "$seed_dir/meta-data"
    cp "$HERE/vm-mon/network-config.yaml" "$seed_dir/network-config"
    genisoimage -quiet -output "$CACHE/vm-mon-seed.iso" -volid cidata -joliet -rock \
      "$seed_dir/user-data" "$seed_dir/meta-data" "$seed_dir/network-config"
    has_vol vm-mon-seed.iso && "${VIRSH[@]}" vol-delete --pool "$POOL" vm-mon-seed.iso
    "${VIRSH[@]}" vol-create-as "$POOL" vm-mon-seed.iso "$(stat -c %s "$CACHE/vm-mon-seed.iso")" --format raw >/dev/null
    "${VIRSH[@]}" vol-upload --pool "$POOL" vm-mon-seed.iso "$CACHE/vm-mon-seed.iso"
    if ! has_vol vm-mon.qcow2; then
      "${VIRSH[@]}" vol-create-as "$POOL" vm-mon.qcow2 "${DISK_GB}G" --format qcow2 \
        --backing-vol "$BASE_VOL" --backing-vol-format qcow2 >/dev/null
    fi
    "${VIRSH[@]}" define "$HERE/vm-mon/domain.xml" >/dev/null
    say "defined $VM"
  fi
  if [ "$("${VIRSH[@]}" domstate "$VM")" != running ]; then
    "${VIRSH[@]}" start "$VM" >/dev/null
    say "started $VM"
  fi
}

step_wait() {
  say "waiting for SSH on $VM_IP and for cloud-init to finish (a few minutes on first boot)"
  local deadline=$((SECONDS + 900))
  until on_vm labadmin true 2>/dev/null; do
    [ $SECONDS -lt $deadline ] || die "no SSH on $VM_IP after 15 minutes"
    sleep 5
  done
  on_vm labadmin "cloud-init status --wait >/dev/null; cloud-init status --long | sed -n '1,3p'"
}

step_provision() {
  say "provisioning as labadmin (system part), then as cim (CIM, skills, cim watch)"
  on_vm labadmin "sudo bash -s -- '$HEXSTRIKE_URL' '$HEXSTRIKE_SHA'" < "$HERE/vm-mon/provision-root.sh"
  on_vm cim "bash -s -- '$REPO_URL' '$REPO_REF'" < "$HERE/vm-mon/provision-cim.sh"
}

step_isolate() {
  if "${VIRSH[@]}" domiflist "$VM" | grep -qi "$NAT_MAC"; then
    "${VIRSH[@]}" detach-interface "$VM" user --mac "$NAT_MAC" --live --config
    say "removed the NAT card ($NAT_MAC): $VM is on $NET only"
  fi
  "${VIRSH[@]}" domiflist "$VM" | grep -qi "$NAT_MAC" && die "the NAT card is still attached"
  step_check
}

step_check() {
  say "checking isolation and CIM on $VM"
  local cards
  cards="$("${VIRSH[@]}" domiflist "$VM" | awk 'NF {print $3}' | sort -u | tr '\n' ' ')"
  [ "$cards" = "$NET " ] || die "$VM networks: $cards (want only $NET)"
  on_vm labadmin 'test -z "$(ip route show default)"' || die "$VM has a default route"
  if on_vm labadmin 'timeout 5 curl -fsS -o /dev/null https://github.com' 2>/dev/null; then
    die "$VM reached the internet"
  fi
  on_vm cim 'cd ~ && ~/.local/bin/uv run --project ~/cim cim status --config ~/cim.toml --require-watch | sed -n 1,3p'
  say "isolated: no default route, no internet; cim watch running"
}

step_snapshot() {
  local name="${1:-base}"
  if "${VIRSH[@]}" snapshot-info "$VM" "$name" >/dev/null 2>&1; then
    say "snapshot $name exists"
    return
  fi
  "${VIRSH[@]}" snapshot-create-as "$VM" "$name" \
    --description "VM-MON $name: CIM $REPO_REF, HexStrike $HEXSTRIKE_SHA, isolated; $(date -u +%FT%TZ)" >/dev/null
  say "snapshot $name taken"
}

step_hexstrike() {
  # T-04 acceptance: HexStrike at the pin, behind cim proxy, lists 150+ tools (offline). Run it
  # after the base snapshot: it writes the server's records to the store.
  on_vm cim 'bash -s' < "$HERE/vm-mon/check-hexstrike.sh"
}

step_destroy() {
  [ "${1:-}" = "--yes" ] || die "destroy removes $VM, its disks and the $NET network: pass --yes"
  "${VIRSH[@]}" destroy "$VM" 2>/dev/null || true
  for snap in $("${VIRSH[@]}" snapshot-list "$VM" --name 2>/dev/null); do
    "${VIRSH[@]}" snapshot-delete "$VM" "$snap" >/dev/null
  done
  "${VIRSH[@]}" undefine "$VM" 2>/dev/null || true
  for vol in vm-mon.qcow2 vm-mon-seed.iso; do
    has_vol "$vol" && "${VIRSH[@]}" vol-delete --pool "$POOL" "$vol" >/dev/null
  done
  "${VIRSH[@]}" net-destroy "$NET" 2>/dev/null || true
  "${VIRSH[@]}" net-undefine "$NET" 2>/dev/null || true
  say "removed $VM and $NET (the base image and the pool are kept)"
}

case "${1:-}" in
  net) step_net ;;
  pool) step_pool ;;
  key) step_key ;;
  image) step_image ;;
  create) step_create ;;
  wait) step_wait ;;
  provision) step_provision ;;
  isolate) step_isolate ;;
  check) step_check ;;
  snapshot) shift; step_snapshot "${1:-base}" ;;
  hexstrike) step_hexstrike ;;
  all) step_net; step_pool; step_key; step_image; step_create; step_wait; step_provision
       step_isolate; step_snapshot base ;;
  ssh) shift; user="${1:-cim}"; shift || true; on_vm "$user" "$@" ;;
  destroy) shift; step_destroy "${1:-}" ;;
  *) sed -n '2,14p' "$0"; exit 2 ;;
esac
