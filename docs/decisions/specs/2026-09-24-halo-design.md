# Halo: design decisions

> Historical record, frozen 2026-09-24. Source code is authoritative; where
> this document and the code disagree, the code wins.

## Why this plugin

On 2026-09-24 the Omarchy plugin catalog had about 25 smart-home plugins.
Roughly ten go through Home Assistant and need a running HA server; the rest
each control one brand (Hue, Govee, WiZ, WLED, Elgato). None controlled
TP-Link Tapo or Kasa lights, and none talked to lights directly without a
server.

## Scope of v1

TP-Link only, because the one light available for testing is a Tapo L920-5
(EU). The adapter interface (`halo/adapters/base.py`) is there so other
brands can be added one at a time, each when someone can test it; a Home
Assistant adapter would cover the long tail.

In v1: power, brightness, color, white temperature, per-segment gradients,
built-in effects, saved looks, theme and wallpaper colors with follow-on-
switch, first-run sign-in and network scan.

Left out on purpose:

- Music-reactive color. Driving the strip from the computer peaks at ~6.7
  full-strip updates a second (measured below), and each update goes through
  `apply_segment_effect_rule`, which the light stores and can read back; it
  probably writes flash every time. The light's own `music_rhythm_v2`
  component is the likely proper channel and is not reverse engineered.
- Lock, sleep and meeting automations. They need a resident listener, and the
  first version is meant to run nothing while unused.
- Screen-color sync. Continuous Wayland capture costs more than the feature
  is worth for a hotkey panel.
- Schedules and sunrise. The light and the Tapo app already do these.

## Measurements behind the architecture

Tapo L920-5 (EU), firmware 1.4.4, Wi-Fi, python-kasa at PR #1592:

| operation | time |
|---|---|
| discovery + handshake + first read | 2.0–3.0 s |
| handshake with cached connection type | 1.9 s |
| one color change (`set_hsv`), sustained | 111 ms median, 9/s, 0 errors in 80 |
| all 50 segments (`apply_segment_effect_rule`), sustained | 148 ms median, 6.7/s, 0 errors in 40 |

The handshake is what shapes everything: a process per command would make
every hotkey press take two seconds. Hence one daemon holding the sessions,
started on demand, exiting after 60 s idle.

Other facts found on the device:

- `set_brightness` switches an active segment rule off. The rule has its own
  `brightness` field, so brightness changes while a gradient is showing
  re-send the rule instead.
- Power off and on keeps the segment rule.
- Broadcast discovery found nothing on this machine (ufw active); unicast
  probes to each host did. The scan does both.

## Rejected alternatives

- **A daemon running all the time.** Would save the first two seconds after
  opening the panel, at the cost of a process 24 hours a day and reconnect
  handling across suspend. The panel shows cached state during the handshake
  instead.
- **A standalone window (GTK or a TUI).** Slower to open than an overlay the
  shell already has loaded, and would not follow the Omarchy theme.
- **Requiring Home Assistant.** Ten plugins already do that.

## Dependency on an unreleased python-kasa

Tapo firmware from 2025 on speaks TPAP; python-kasa 0.10.2, the latest
release, rejects it with `UnsupportedDeviceError`. PR #1592 adds it and works
against this L920. `scripts/setup` pins commit `e708447`; replace with a
version number when the PR is released.
