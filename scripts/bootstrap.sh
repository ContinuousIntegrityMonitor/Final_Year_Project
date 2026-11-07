#!/usr/bin/env bash
# bootstrap.sh — run once after cloning, and after any dependency change.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

usage() {
  cat <<'EOF'
Usage: scripts/bootstrap.sh [--help]

Create .venv, sync locked dependencies with uv, install pre-commit hooks.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "FAIL: uv not found. Install: https://docs.astral.sh/uv/"
  exit 1
fi

uv python install 3.12
uv venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
uv sync --all-extras
uv tool install pre-commit || true
pre-commit install
echo "OK: bootstrap complete. Next: scripts/check-env.sh --dev"
