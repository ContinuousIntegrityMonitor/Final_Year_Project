# LAB STAND-IN for a helper that stays behind after it exits (threat A3). Inert.
# It leaves a detached background process and drops an autostart entry in $HOME.
# The process only sleeps, and the autostart entry only runs `true`.
mkdir -p "$HOME/.config/autostart"
printf '[Desktop Entry]\nType=Application\nName=cache-warmer\nExec=true\n' \
  > "$HOME/.config/autostart/cache-warmer.desktop"
( sleep 120 & )
echo "cache warm"
