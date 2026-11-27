#!/usr/bin/env bash
# VM-TGT setup, run as root by `scripts/lab/lab.sh vm-tgt provision` (through labadmin).
# Pulls the targets once (while the passt card is attached), records their digests in
# /opt/targets/images.lock, and starts them with restart=unless-stopped, so they come back on
# every boot without the internet.
set -euo pipefail
cloud-init status --wait >/dev/null || true
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq docker.io docker-compose-v2 curl qemu-guest-agent >/dev/null
systemctl enable --now docker qemu-guest-agent >/dev/null 2>&1

install -d -m 0755 /opt/targets
cat > /opt/targets/compose.yaml <<'YAML'
# CIM lab targets (T-04): vulnerable versions for benign scanning workloads from VM-MON.
#   httpd 2.4.49   CVE-2021-41773 (path traversal)      port 80
#   tomcat 8.5.19  CVE-2017-12617 (JSP upload via PUT)  port 8080
#   redis 4.0.14   unauthenticated access               port 6379
# Lab only: these must never be reachable from any real network.
name: cim-targets
services:
  httpd:
    image: vulhub/httpd:2.4.49
    ports: ["80:80"]
    restart: unless-stopped
  tomcat:
    image: vulhub/tomcat:8.5.19
    ports: ["8080:8080"]
    restart: unless-stopped
  redis:
    image: vulhub/redis:4.0.14
    ports: ["6379:6379"]
    restart: unless-stopped
YAML
docker compose -f /opt/targets/compose.yaml pull --quiet
docker compose -f /opt/targets/compose.yaml up -d --quiet-pull 2>&1 | tail -3
for image in vulhub/httpd:2.4.49 vulhub/tomcat:8.5.19 vulhub/redis:4.0.14; do
  docker image inspect --format '{{index .RepoDigests 0}}' "$image"
done | tee /opt/targets/images.lock
echo "provision-root: targets up: $(docker compose -f /opt/targets/compose.yaml ps --services --status running | tr '\n' ' ')"
