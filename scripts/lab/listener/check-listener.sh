#!/usr/bin/env bash
# LISTENER check, run as root by `scripts/lab/lab.sh listener check`: the service listens.
set -euo pipefail
systemctl is-active --quiet cim-listener.service
ports="$(ss -ltnH | awk '{print $4}' | sed 's/.*://' | sort -n | uniq | tr '\n' ' ')"
echo "check-listener: cim-listener active; listening on $ports"
for p in 80 443 4444 8080 9000; do case " $ports" in *" $p "*) ;; *) echo "port $p missing"; exit 1 ;; esac; done
