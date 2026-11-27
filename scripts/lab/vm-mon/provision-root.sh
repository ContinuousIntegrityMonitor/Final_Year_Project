#!/usr/bin/env bash
# VM-MON system setup, run as root by `scripts/lab/lab.sh vm-mon provision` (through labadmin).
# Environment: HEXSTRIKE_URL HEXSTRIKE_SHA (from corpora/mcp/hexstrike.pin).
#
# - /opt/skills and /opt/mcp belong to cim, the operator: skills and MCP servers are installed
#   by the user who runs them, which is what CIM watches.
# - HexStrike is checked out at the pinned commit (never master) with its own virtualenv.
set -euo pipefail
HEXSTRIKE_URL="${HEXSTRIKE_URL:-$1}"
HEXSTRIKE_SHA="${HEXSTRIKE_SHA:-$2}"

cloud-init status --wait >/dev/null || true  # its result is checked below, not trusted
id cim >/dev/null

# What cloud-init's packages and runcmd do, again: a first boot whose installs failed (no network
# yet, a mirror down) is repaired here instead of leaving a half-built VM.
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git strace curl ca-certificates jq python3 python3-venv python3-pip \
  docker.io qemu-guest-agent >/dev/null
usermod -aG docker cim
loginctl enable-linger cim
systemctl enable --now docker qemu-guest-agent >/dev/null 2>&1
install -d -o cim -g cim -m 0755 /opt/skills /opt/mcp

if [ ! -d /opt/mcp/hexstrike/.git ]; then
  sudo -u cim git clone --quiet "$HEXSTRIKE_URL" /opt/mcp/hexstrike
fi
sudo -u cim git -C /opt/mcp/hexstrike fetch --quiet origin
sudo -u cim git -C /opt/mcp/hexstrike -c advice.detachedHead=false checkout --quiet "$HEXSTRIKE_SHA"
[ "$(sudo -u cim git -C /opt/mcp/hexstrike rev-parse HEAD)" = "$HEXSTRIKE_SHA" ]
if [ ! -x /opt/mcp/hexstrike/.venv/bin/python ]; then
  sudo -u cim python3 -m venv /opt/mcp/hexstrike/.venv
fi
sudo -u cim /opt/mcp/hexstrike/.venv/bin/pip install --quiet --upgrade pip
sudo -u cim /opt/mcp/hexstrike/.venv/bin/pip install --quiet -r /opt/mcp/hexstrike/requirements.txt
echo "provision-root: HexStrike $(sudo -u cim git -C /opt/mcp/hexstrike rev-parse --short HEAD) in /opt/mcp/hexstrike"

systemctl is-active --quiet docker && echo "provision-root: docker active"
echo "provision-root: strace $(strace -V | head -1 | awk '{print $NF}'), linger $(loginctl show-user cim -p Linger --value)"
