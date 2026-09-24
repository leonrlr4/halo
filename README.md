# Halo

The lights in the room, from a hotkey. Press `SUPER + SHIFT + L` and a panel
opens over whatever you are doing: power, brightness, a color wheel, white
temperature, per-segment gradients for light strips, the light's built-in
effects, and the colors of your Omarchy theme, following it as you switch.

Halo talks to TP-Link Tapo and Kasa lights and plugs directly on your local
network. There is no cloud relay and no Home Assistant.

## What it does

**Color and white.** A hue and saturation wheel, a white temperature slider
across the light's own range, and one-click swatches.

**Gradients along the strip.** On strips with independently lit segments
(a Tapo L920 has 50), the Gradient tab lays colors along the strip. Click the
bar to add a stop, drag stops to move them, right-click one to remove it.
Reverse, mirror and even-out apply to the whole gradient, and eight presets
give you a starting point. Every edit goes to the strip as you make it.

**Your theme on the wall.** The Theme tab takes the accent and ANSI colors of
the current Omarchy theme, or the dominant colors of the wallpaper, drops
the greys an LED cannot show, and lays the rest along the strip as a
gradient, a mirrored gradient, solid blocks or the accent alone. Turn on
*Follow theme changes* and the lights repaint every time you switch themes,
with the panel closed.

**Scenes.** Save a gradient with `S` and it appears in Scenes next to the
effects built into the light (Aurora, Sunset, Rainbow and the rest).

**Several lights.** Add every light on the network; `Tab` cycles between
them and *All*, which sends each change to every light at once.

## Keys

| Key | Does |
|---|---|
| `SUPER + SHIFT + L` | open or close the panel |
| `Space` | power |
| `←` `→` (or `h` `l`) | brightness by 5, with `Shift` by 1 |
| `1` – `4` | Color, Gradient, Theme, Scenes |
| `T` | apply the theme colors now |
| `S` | save the gradient to Scenes |
| `Tab` | next light, or all of them |
| `Esc` / `q` | close |

## Install

```bash
omarchy plugin add https://github.com/leonrlr4/halo --enable
~/.config/omarchy/plugins/leonrlr4.halo/scripts/setup
hyprctl reload
```

`scripts/setup` builds a private Python environment for the Tapo protocol
library, binds the key and installs the theme hook. It is safe to re-run;
`scripts/setup --check` reports without changing anything, and
`--key "SUPER + ALT + L"` picks a different key. It refuses a key Hyprland
already uses.

Then open the panel and sign in with the email and password of your TP-Link
(Tapo) account. Tapo lights accept local control only from their owner's
account, so this is required even though nothing goes through TP-Link's
servers. The password is stored in your desktop keyring (via `secret-tool`),
never in a file. Halo then scans the network and lists the lights it finds.

Requires `python`, `git`, `jq` and `secret-tool` (libsecret), all present on
a stock Omarchy install. ImageMagick is needed for wallpaper colors.

## From a terminal or another key

```bash
halo=~/.config/omarchy/plugins/leonrlr4.halo/bin/halo
$halo toggle            # every light; --device ID for one
$halo bright +10
$halo color 200 90      # hue 0-359, saturation 0-100
$halo temp 2700
$halo theme             # apply the current theme's colors now
$halo status
```

Bind any of these in `bindings.lua` for keys that change the light without
opening the panel.

## How it runs

A Tapo light takes about two seconds to accept a new session, then around a
tenth of a second per command. So one small daemon holds the connection to
every light, and the panel, the command line and the theme hook all talk to
it over a unix socket in `$XDG_RUNTIME_DIR`. It starts when something needs
it and exits after a minute with nothing to do. While the panel is closed and
the lights are left alone, no Halo process is running.

Dragging a slider sends far more changes than a light can take. The daemon
keeps only the newest pending change of each kind, so the light always moves
straight to where the slider is now.

## Compatibility

Tested on a Tapo L920-5 (EU), firmware 1.4.4. Other Tapo and Kasa bulbs,
strips and plugs supported by [python-kasa](https://github.com/python-kasa/python-kasa)
should work; the panel shows only the controls a device reports (a plug gets
a power switch, a white-only bulb no color wheel).

Recent Tapo firmware uses a new encryption scheme, TPAP, that no released
version of python-kasa supports yet. Halo installs the branch from
[python-kasa#1592](https://github.com/python-kasa/python-kasa/pull/1592),
pinned to a tested commit, until it is released.

## Uninstall

```bash
~/.config/omarchy/plugins/leonrlr4.halo/scripts/uninstall
omarchy plugin remove leonrlr4.halo
```

`uninstall` removes the key, the hook, the Python environment, the config and
the keyring entry; `--keep-data` keeps the config and the password.

## License

MIT
