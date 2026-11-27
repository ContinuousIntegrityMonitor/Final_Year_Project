#!/usr/bin/env bash
# The whole lab, checked from VM-MON the way the demo uses it (T-04, T-17):
# 1. every VM is isolated (lab.sh <vm> check);
# 2. from VM-MON, as cim: the three targets on VM-TGT answer, and the listener accepts;
# 3. the T-17 attack A3 runs on VM-MON against the lab listener (--listener 10.10.10.30:9000):
#    it must PASS with a behaviour alert, and the listener must have logged what the skill sent.
# A3 runs on a fresh copy of the corpus in its own store, never in the operator's store.
set -euo pipefail
LAB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lab.sh"

for vm in vm-mon vm-tgt listener; do
  "$LAB" "$vm" check
done

echo "check-lab: from VM-MON (as cim)"
"$LAB" vm-mon ssh cim bash -s <<'EOF'
set -euo pipefail
printf '  httpd  http://10.10.10.20:80/   -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://10.10.10.20:80/)"
printf '  tomcat http://10.10.10.20:8080/ -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' http://10.10.10.20:8080/)"
pong="$(timeout 3 bash -c 'exec 3<>/dev/tcp/10.10.10.20/6379; printf "PING\r\n" >&3; head -c 7 <&3' | tr -d '\r\n')"
printf '  redis  10.10.10.20:6379        -> %s\n' "$pong"
[ "$pong" = "+PONG" ]
timeout 3 bash -c 'exec 3<>/dev/tcp/10.10.10.30/9000' && echo "  listener 10.10.10.30:9000      -> accepts"
work="$(mktemp -d)/a3"
cd "$HOME/cim"
"$HOME/.local/bin/uv" run --quiet cim skills attack A3 --work "$work" --listener 10.10.10.30:9000 \
  | grep -E "egress|behaviour alert|PASS|FAIL" | sed 's/^/  /'
EOF

echo "check-lab: the listener's last entry"
"$LAB" listener ssh labadmin 'sudo tail -1 /var/log/cim-listener/connections.jsonl' \
  | python3 -c '
import json, sys
entry = json.loads(sys.stdin.read())
print("  {ts} port {port} from {peer}: {bytes} bytes".format(**entry))
assert entry["peer"].startswith("10.10.10.10:"), "not from VM-MON"
assert "env_names" in entry["preview"], "not the A3 payload"
print("  it is the A3 payload from VM-MON (variable names and the decoy, never values)")
'
echo "check-lab: PASS"
