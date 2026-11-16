#!/usr/bin/env bash
# Box Cat: a cat jumping over boxes on the Touch Bar. Safe to run again.
source "$(dirname "$(readlink -f "$0")")/lib.sh"

pacman -Q tiny-dfr >/dev/null 2>&1 || die "tiny-dfr isn't installed. Install it from the arch-mact2 repo first (pacman -S tiny-dfr)."
command -v hyprctl >/dev/null || die "This plugin needs Hyprland."
missing=()
command -v cargo >/dev/null || missing+=(rust)
command -v git >/dev/null || missing+=(git)

if [[ ${1:-} != --yes ]]; then
  cat <<MSG
This will:
  - install ${missing[*]:-nothing extra} with pacman (needs your password)
  - build tiny-dfr-plus (tiny-dfr $PLUS_COMMIT plus tiny-dfr-plus.patch) in $PLUS_CACHE,
    install it as /usr/local/bin/tiny-dfr-plus and point tiny-dfr.service at it
    (shared with other Touch Bar plugins; the packaged tiny-dfr is left alone)
  - add a binding for $GAME_KEYS to $BINDINGS, between marker comments
  - add the user service $USER_UNIT, which runs the game only while you play
Run remove.sh at any time to undo all of it.
MSG
  if [[ -t 0 ]]; then
    read -rp "Continue? [y/N] " answer
    [[ $answer == [yY]* ]] || { echo "Nothing changed."; exit 0; }
  else
    die "Run this in a terminal to confirm, or pass --yes."
  fi
fi

if (( ${#missing[@]} )); then
  say "Installing ${missing[*]}"
  as_root pacman -S --needed --noconfirm "${missing[@]}"
fi

say "Building tiny-dfr-plus"
built="$(plus_build "$PLUGIN_DIR/tiny-dfr-plus.patch")"

say "Installing it"
as_root "$PLUGIN_DIR/tiny-dfr-plus-root.sh" install "$PLUGIN_ID" "$built"

say "Adding the game service"
mkdir -p "$USER_UNIT_DIR"
cat >"$USER_UNIT_DIR/$USER_UNIT" <<UNIT
[Unit]
Description=Box Cat on the Touch Bar ($PLUGIN_ID)

[Service]
# Hyprland holds plain Space while the game runs, so jumping doesn't type spaces.
ExecStartPre=-/usr/bin/hyprctl eval 'hl.bind("SPACE", function() end, { description = "Box Cat: jump" })'
ExecStart=/usr/bin/python3 -I $PLUGIN_DIR/game/cat.py
ExecStopPost=-/usr/bin/hyprctl eval 'hl.unbind("SPACE")'
UNIT
systemctl --user daemon-reload

say "Binding $GAME_KEYS"
remove_binding
cat >>"$BINDINGS" <<LUA
$MARK_BEGIN
-- Box Cat on the Touch Bar. Managed by the touchbar-cat plugin; run its remove.sh to undo.
o.bind("$GAME_KEYS", "Box Cat (Touch Bar game)", "$PLUGIN_DIR/game/toggle.sh")
$MARK_END
LUA
reload_hyprland

say "Done. Press ${GAME_KEYS// /} to play; Space jumps, Esc or ${GAME_KEYS// /} again quits."
