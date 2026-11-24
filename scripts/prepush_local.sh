#!/usr/bin/env bash
# Local pre-push gates for developer machines (called by scripts/_ship.sh).
# Ubuntu CI (.github/workflows/ci-push.yml) still runs the full suite.
# On Windows: common + MCP + dashboard only (skills host tests need Linux).
set -euo pipefail

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Usage: scripts/prepush_local.sh

Run local pre-push gates (ruff, mypy, unit tests, scripts --help).
On Windows: common+MCP(+dashboard) tests only; skip check-env --ci.
Ubuntu CI still runs the full suite.
EOF
  exit 0
fi

cd "$(dirname "$0")/.."

_windows=0
case "$(uname -s 2>/dev/null || echo unknown)" in
  MINGW*|MSYS*|CYGWIN*) _windows=1 ;;
esac
if [[ -n "${WINDIR:-}" || -n "${SystemRoot:-}" ]]; then
  _windows=1
fi

echo "== uv sync (locked dev tools) =="
uv sync --all-extras -q
echo "== ruff format =="
uv run ruff format --check .
echo "== ruff check =="
uv run ruff check .
echo "== mypy =="
uv run mypy src/cim
echo "== import smoke =="
uv run pytest tests/common/test_imports.py -q

if [[ "$_windows" -eq 1 ]]; then
  echo "== unit tests + coverage (Windows: common + MCP + dashboard) =="
  # Skills host suite needs Linux (strace, cgroup, non-UTF8 names, .sh helpers).
  # Cover only packages exercised here so --cov-fail-under stays meaningful.
  # HTTP dashboard tests: flaky WinError 10053 on this host; Ubuntu CI covers them.
  # 10k-append timing is host-noisy on Windows; Ubuntu CI still enforces it.
  uv run pytest tests/common tests/mcp -m "not sys and not lab" \
    --deselect tests/mcp/test_dashboard.py::test_http_serves_readonly_by_default \
    --deselect tests/mcp/test_dashboard.py::test_demo_write_requires_token \
    --deselect tests/mcp/test_dashboard.py::test_button_calls_the_artificial_mcp \
    --deselect tests/mcp/test_dashboard.py::test_tamper_breaks_the_next_fingerprint \
    --deselect tests/mcp/test_dashboard.py::test_clear_wipes_the_demo \
    --deselect tests/common/test_store.py::test_ten_thousand_appends_under_five_seconds \
    --cov=cim.common --cov=cim.mcp --cov=cim.dashboard \
    --cov-report=term-missing --cov-fail-under=60 -q
else
  echo "== unit tests + coverage =="
  uv run pytest -m "not sys and not lab" --cov=cim --cov-report=term-missing --cov-fail-under=60 -q
fi

echo "== scripts --help (skip scripts/_*) =="
shopt -s nullglob
_self=$(basename "$0")
for f in scripts/*; do
  base=$(basename "$f")
  case "$base" in
    _*|$_self) echo "skip $f"; continue ;;
  esac
  case "$f" in
    *.sh)
      # Bound each --help so a stuck script cannot hang the ship forever.
      if command -v timeout >/dev/null 2>&1; then
        timeout 15 bash "$f" --help >/dev/null
      else
        bash "$f" --help >/dev/null
      fi
      ;;
    *.py) uv run python "$f" --help >/dev/null ;;
    *) echo "skip $f"; continue ;;
  esac
  echo "OK help: $f"
done
echo "== check-env --ci =="
chmod +x scripts/check-env.sh || true
if [[ "$_windows" -eq 1 ]]; then
  # docker hello-world in check-env can hang forever on this host; CI runs it on Ubuntu.
  echo "skip check-env --ci on Windows (CI covers it)"
else
  uv run bash scripts/check-env.sh --ci
fi
echo "ALL LOCAL GATES PASSED"
