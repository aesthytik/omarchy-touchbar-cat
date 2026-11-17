# Box Cat

A tiny endless runner for the MacBook Touch Bar: a pixel cat runs along the bar and you
jump it over cardboard boxes. It speeds up the longer you last, and your best score is
kept.

- **Super + Ctrl + G** starts the game, and stops it again.
- **Space** (or Up, or a tap on the bar) jumps.
- **Esc**, or tapping the red x at the right end, quits.

While the game runs it uses the whole Touch Bar; your normal keys come back as soon as
it stops. Hyprland holds plain Space while you play, so jumping doesn't type spaces
into the focused window. Space is released again when the game stops, however it stops.

## Requirements

- An Intel MacBook Pro with a Touch Bar (T2), running Omarchy with the `linux-t2` kernel
- `tiny-dfr` from the `arch-mact2` repo, already working
- `rust` and `git` to build tiny-dfr-plus (setup installs them if they're missing)

## Install

```bash
omarchy plugin add https://github.com/aesthytik/omarchy-touchbar-cat --enable
~/.config/omarchy/plugins/io.github.aesthytik.touchbar-cat/setup.sh
```

Setup lists what it will change and asks before doing anything (pass `--yes` to skip the
question). It needs your password once. It:

1. installs `rust` and `git` if they're missing;
2. builds **tiny-dfr-plus** in `~/.cache/tiny-dfr-plus/`: tiny-dfr at a pinned commit
   plus `tiny-dfr-plus.patch` (takes a minute or two the first time);
3. installs it as `/usr/local/bin/tiny-dfr-plus` and points `tiny-dfr.service` at it with
   the drop-in `/etc/systemd/system/tiny-dfr.service.d/50-tiny-dfr-plus.conf`; the packaged
   `/usr/bin/tiny-dfr` is left untouched;
4. adds the user service `touchbar-cat.service`, which only runs while you play;
5. adds the Super + Ctrl + G binding to `~/.config/hypr/bindings.lua`, between marker comments.

After a `tiny-dfr` package update, run setup again to rebuild.

## How it draws on the Touch Bar

`tiny-dfr-plus.patch` lets a local program take over the whole bar: it sends frames
(`TDT1`, width, height, one RGB332 byte per pixel) to the unix socket
`/run/tiny-dfr/takeover.sock`, and the bar shows them until they stop for half a second. While a
program has the bar, tiny-dfr sends it only Esc, Space, Up and Down presses and touches
on the bar; no other typing is passed on. The game draws at 1085×30 and tiny-dfr scales
it 2× to the bar's 2170×60 pixels.

### Who can use the sockets

tiny-dfr-plus's sockets are files in `/run/tiny-dfr/`, a directory systemd creates for
the daemon and only root can write to, so no other account can claim their names first.
For every frame the kernel tells the daemon which user sent it; frames from anyone but
the user logged in at the screen (or root) are dropped, and only that user is sent key
and touch events. Programs check that events come from `/run/tiny-dfr/…` before using
them.

The same patch has a full-colour backdrop socket (`/run/tiny-dfr/backdrop.sock`) used by
Touch Bar Scenes, with the same checks. Its key-column events, which say roughly where on
the keyboard a key was pressed but never which key, are off unless `KeyPulses = true` is
set in `/etc/tiny-dfr/config.toml`.

The patch is built from a fixed upstream tiny-dfr commit (`a79f2f4`), fetched by its full
SHA and checked out detached before building.

tiny-dfr-plus is shared with the
[Touch Bar Waveform](https://github.com/aesthytik/omarchy-touchbar-waveform) plugin. Each
plugin registers in `/etc/tiny-dfr/plus.d/`, and the stock tiny-dfr comes back when the
last one is removed.

## Remove

```bash
~/.config/omarchy/plugins/io.github.aesthytik.touchbar-cat/remove.sh
omarchy plugin remove io.github.aesthytik.touchbar-cat
```

Remove stops and deletes the game service, removes the binding and releases
tiny-dfr-plus. Your best score stays in `~/.local/state/touchbar-cat/highscore`; delete
that file to reset it. `rust` stays installed; remove it with pacman if you don't need it.

## Credits

The cat, boxes and font are original pixel art made for this plugin. `preview.png` is an
illustration of the game, not a photo.

## License

MIT. The patch applies to tiny-dfr, which is MIT and Apache-2.0 licensed.
