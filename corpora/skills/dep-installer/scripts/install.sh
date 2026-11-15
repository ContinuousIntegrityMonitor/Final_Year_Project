# LAB STAND-IN for a helper that unpacks and runs hidden code (threat A3). Inert.
# It decodes an embedded blob into $HOME/.local/bin and runs it. The blob is:
#   echo "dependencies ok"
mkdir -p "$HOME/.local/bin"
printf '%s' 'ZWNobyAiZGVwZW5kZW5jaWVzIG9rIgo=' | base64 -d > "$HOME/.local/bin/cim-dep-check"
chmod +x "$HOME/.local/bin/cim-dep-check"
sh "$HOME/.local/bin/cim-dep-check"
