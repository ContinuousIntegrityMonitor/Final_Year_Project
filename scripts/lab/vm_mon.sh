#!/usr/bin/env bash
# VM-MON, the CIM lab's monitored host: `scripts/lab/lab.sh vm-mon ...` (see lab.sh for steps).
#
#   scripts/lab/vm_mon.sh all | <step> | ssh [user] [command...] | destroy --yes
#   scripts/lab/vm_mon.sh hexstrike     # T-04 acceptance: HexStrike lists 150+ tools via cim proxy
set -euo pipefail
LAB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lab.sh"
case "${1:-}" in
  hexstrike) exec "$LAB" vm-mon run cim check-hexstrike.sh ;;
  *) exec "$LAB" vm-mon "$@" ;;
esac
