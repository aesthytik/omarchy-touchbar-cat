#!/usr/bin/env bash
# Super+Ctrl+G: start the game, or stop it if it's running.
if systemctl --user is-active --quiet touchbar-cat.service; then
  systemctl --user stop touchbar-cat.service
else
  systemctl --user start touchbar-cat.service
fi
