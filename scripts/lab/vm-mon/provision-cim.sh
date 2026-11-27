#!/usr/bin/env bash
# VM-MON operator setup, run as cim by `scripts/lab/lab.sh vm-mon provision`, following
# docs/setup/cim-pipeline.md: install, cim.toml, first inventory, cim watch under systemd.
# Environment: REPO_URL REPO_REF.
set -euo pipefail
REPO_URL="${REPO_URL:-$1}"
REPO_REF="${REPO_REF:-$2}"
UV_VERSION=0.13.0
UV="$HOME/.local/bin/uv"

if [ ! -x "$UV" ]; then
  curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" | env UV_NO_MODIFY_PATH=1 sh >/dev/null
fi

if [ ! -d "$HOME/cim/.git" ]; then
  git clone --quiet "$REPO_URL" "$HOME/cim"
fi
git -C "$HOME/cim" fetch --quiet origin
git -C "$HOME/cim" -c advice.detachedHead=false checkout --quiet "origin/$REPO_REF" 2>/dev/null \
  || git -C "$HOME/cim" -c advice.detachedHead=false checkout --quiet "$REPO_REF"
(cd "$HOME/cim" && "$UV" sync --quiet --all-extras)
CIM=("$UV" run --quiet --project "$HOME/cim" cim)
echo "provision-cim: CIM $(git -C "$HOME/cim" rev-parse --short HEAD) ($REPO_REF), $("${CIM[@]}" version)"

# The seed skill corpus, installed where an operator installs skills (not the attack inputs).
for skill in "$HOME"/cim/corpora/skills/*/; do
  name="$(basename "$skill")"
  [ "$name" = _attacks ] && continue
  [ -d "/opt/skills/$name" ] || cp -r "$skill" "/opt/skills/$name"
done

cd "$HOME"
if [ ! -f cim.toml ]; then
  "${CIM[@]}" init cim.toml --origin vm-mon --skill-root /opt/skills --db cim-data/cim-store.sqlite
  cat >> cim.toml <<'EOF'

[mcp.servers.hexstrike]
root = "/opt/mcp/hexstrike"
origin = "vm-mon"
minimum_tools = 150
EOF
fi
mkdir -p cim-data
"${CIM[@]}" inventory --config cim.toml --side skills

mkdir -p "$HOME/.config/systemd/user"
"${CIM[@]}" init cim.toml --systemd > "$HOME/.config/systemd/user/cim-watch.service"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
systemctl --user daemon-reload
systemctl --user enable --now cim-watch.service >/dev/null 2>&1
sleep 3
systemctl --user is-active cim-watch.service
"${CIM[@]}" status --config cim.toml --require-watch | sed -n 1,3p
