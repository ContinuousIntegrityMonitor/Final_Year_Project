#!/usr/bin/env bash
# VM-MON check, run as cim by `scripts/lab/lab.sh vm-mon check`: cim watch runs, the chain verifies.
set -euo pipefail
cd "$HOME"
"$HOME/.local/bin/uv" run --quiet --project "$HOME/cim" cim status --config cim.toml --require-watch | sed -n 1,3p
