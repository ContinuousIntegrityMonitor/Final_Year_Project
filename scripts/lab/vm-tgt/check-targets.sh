#!/usr/bin/env bash
# VM-TGT check, run as root by `scripts/lab/lab.sh vm-tgt check`: the three targets answer.
set -euo pipefail
running="$(docker compose -f /opt/targets/compose.yaml ps --services --status running | sort | tr '\n' ' ')"
[ "$running" = "httpd redis tomcat " ] || { echo "check-targets: running: $running"; exit 1; }
http="$(curl -s -o /dev/null -w '%{http_code}' http://10.10.10.20:80/)"
tomcat="$(curl -s -o /dev/null -w '%{http_code}' http://10.10.10.20:8080/)"
redis="$(timeout 3 bash -c 'exec 3<>/dev/tcp/10.10.10.20/6379; printf "PING\r\n" >&3; head -c 7 <&3' | tr -d '\r\n')"
echo "check-targets: httpd $http, tomcat $tomcat, redis $redis (pinned: $(wc -l < /opt/targets/images.lock) digests)"
[ "$redis" = "+PONG" ]
