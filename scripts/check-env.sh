#!/usr/bin/env bash
# check-env.sh --dev | --ci  (exit nonzero on any FAIL)
set -euo pipefail

MODE="${1:-}"
usage() {
  cat <<'EOF'
Usage: scripts/check-env.sh --dev | --ci | --help

Verify the CIM development / CI environment.
EOF
}

if [[ "$MODE" == "--help" || "$MODE" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "$MODE" != "--dev" && "$MODE" != "--ci" ]]; then
  usage
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FAIL=0

pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; FAIL=1; }

# Python >= 3.12
if command -v python >/dev/null 2>&1; then
  PYVER="$(python -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
  python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)' \
    && pass "python >= 3.12 ($PYVER)" || fail "python >= 3.12 (found $PYVER)"
else
  fail "python not found"
fi

# Virtualenv (dev) / allow CI without insisting on VIRTUAL_ENV name
if [[ "$MODE" == "--dev" ]]; then
  if [[ -n "${VIRTUAL_ENV:-}" ]]; then
    pass "running inside a virtualenv"
  elif [[ -f .venv/bin/activate ]]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pass "activated .venv"
  else
    fail "running inside a virtualenv (never global python)"
  fi
else
  pass "ci mode (venv managed by runner)"
fi

# Import smoke
if python - <<'PY'
import cim, cim.mcp, cim.skills, cim.common, cim.common.schema
print("ok")
PY
then
  pass "import cim, cim.mcp, cim.skills, ..."
else
  fail "import cim package"
fi

# CLI
if command -v cim >/dev/null 2>&1; then
  cim --help >/dev/null && pass "cim --help" || fail "cim --help"
else
  python -m cim.cli --help >/dev/null 2>&1 && pass "cim --help (python -m)" || fail "cim --help"
fi

# Docker (optional soft-fail messaging but counts as fail in --dev)
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    if docker run --rm hello-world >/dev/null 2>&1; then
      pass "docker daemon reachable (hello-world)"
    else
      fail "docker hello-world"
    fi
  else
    if [[ "$MODE" == "--ci" ]]; then
      pass "docker skipped in CI (not required for unit gate)"
    else
      fail "docker daemon reachable"
    fi
  fi
else
  if [[ "$MODE" == "--ci" ]]; then
    pass "docker skipped in CI (not required for unit gate)"
  else
    fail "docker not installed"
  fi
fi

# pre-commit hooks [--dev only]
if [[ "$MODE" == "--dev" ]]; then
  if [[ -f .git/hooks/pre-commit ]]; then
    pass "pre-commit hooks installed"
  else
    fail "pre-commit hooks installed"
  fi
  if git config user.name >/dev/null && git config user.email >/dev/null; then
    pass "git identity configured"
  else
    fail "git identity configured"
  fi
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "FAIL? -> fix the environment BEFORE writing any code"
  exit 1
fi
echo "OK: environment checks passed ($MODE)"
