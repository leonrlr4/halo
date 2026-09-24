"""Colour maths: theme palettes in, per-segment states out.

Everything here is pure except the two readers at the bottom, so the layouts
can be tested without a light, a theme or ImageMagick.

A colour is (hue 0-359, saturation 0-100) throughout. Value is left out on
purpose: an LED strip has one brightness, set separately, and a dark theme
colour sent as a low value just makes that stretch of the strip go out.
"""

from __future__ import annotations

import colorsys
import re
import subprocess
from pathlib import Path

HS = tuple[int, int]

# Theme colours below this saturation read as white on an LED, and every
# Omarchy theme has several of them (foreground, selection, greys).
MIN_SATURATION = 18
# Below this value a colour is a background shade, not a hue anyone chose.
MIN_VALUE = 25
# Two colours closer than this in hue look identical on the strip.
MIN_HUE_GAP = 14

LAYOUTS = ("gradient", "mirror", "blocks", "solid")


def hex_to_hsv(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise ValueError(f"not a hex colour: {value!r}")
    r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return round(h * 360) % 360, round(s * 100), round(v * 100)


def hs_to_hex(hs: HS) -> str:
    r, g, b = colorsys.hsv_to_rgb(hs[0] / 360, hs[1] / 100, 1.0)
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def hue_distance(a: int, b: int) -> int:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def pick_vivid(colors: list[str], limit: int = 5) -> list[HS]:
    """The colours of a palette an LED can show, first occurrence wins.

    Order is kept, so the theme's accent stays first; walk_hues decides the
    order they go along the strip.
    """
    picked: list[HS] = []
    for c in colors:
        try:
            h, s, v = hex_to_hsv(c)
        except ValueError:
            continue
        if s < MIN_SATURATION or v < MIN_VALUE:
            continue
        if any(hue_distance(h, p[0]) < MIN_HUE_GAP for p in picked):
            continue
        picked.append((h, s))
        if len(picked) == limit:
            break
    return picked


def walk_hues(colors: list[HS]) -> list[HS]:
    """Keep the first colour, then go round the hue circle from it.

    Theme order puts unrelated hues side by side (accent, then red, then
    green), and a gradient between neighbours that far apart sweeps through
    every hue in between. Walking round the circle keeps each step short.
    """
    if len(colors) < 3:
        return list(colors)
    first = colors[0]
    return [first] + sorted(colors[1:], key=lambda c: (c[0] - first[0]) % 360)


def vivid(hs: HS, amount: float = 0.65) -> HS:
    """Push saturation towards 100.

    Omarchy themes are mostly pastel. Sent as-is, a 35%-saturated mint is
    indistinguishable from white on the strip, because the LEDs have no
    ambient light to be pastel against.
    """
    h, s = hs
    return h, round(s + (100 - s) * amount)


def lerp_hs(a: HS, b: HS, t: float) -> HS:
    """Interpolate along the shorter way round the hue circle."""
    d = (b[0] - a[0]) % 360
    if d > 180:
        d -= 360
    return round(a[0] + d * t) % 360, round(a[1] + (b[1] - a[1]) * t)


def gradient(stops: list[HS], n: int) -> list[HS]:
    if not stops:
        raise ValueError("a gradient needs at least one colour")
    if len(stops) == 1 or n == 1:
        return [stops[0]] * n
    out = []
    span = len(stops) - 1
    for i in range(n):
        pos = i / (n - 1) * span
        k = min(int(pos), span - 1)
        out.append(lerp_hs(stops[k], stops[k + 1], pos - k))
    return out


def gradient_at(stops: list[tuple[float, HS]], n: int) -> list[HS]:
    """A gradient whose stops sit at chosen positions (0-1) along the strip."""
    if not stops:
        raise ValueError("a gradient needs at least one colour")
    stops = sorted(stops, key=lambda s: s[0])
    out = []
    for i in range(n):
        x = i / (n - 1) if n > 1 else 0.0
        if x <= stops[0][0]:
            out.append(stops[0][1])
            continue
        if x >= stops[-1][0]:
            out.append(stops[-1][1])
            continue
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if p0 <= x <= p1:
                t = 0.0 if p1 == p0 else (x - p0) / (p1 - p0)
                out.append(lerp_hs(c0, c1, t))
                break
    return out


def layout(colors: list[HS], n: int, kind: str) -> list[HS]:
    if not colors:
        raise ValueError("no colours to lay out")
    if kind == "solid":
        return [colors[0]] * n
    if kind == "gradient":
        return gradient(colors, n)
    if kind == "mirror":
        # There and back, so both ends of the strip match: the join is
        # invisible when the strip runs round a room or a desk edge.
        return gradient(colors + colors[-2::-1], n)
    if kind == "blocks":
        return [colors[min(i * len(colors) // n, len(colors) - 1)] for i in range(n)]
    raise ValueError(f"unknown layout: {kind!r} (expected one of {', '.join(LAYOUTS)})")


# ---- readers ---------------------------------------------------------------

THEME_DIR = Path.home() / ".local/state/omarchy/current/theme"
WALLPAPER = Path.home() / ".local/state/omarchy/current/background"

# The accent first, then the bright and normal ANSI hues. color0/7/8/15 are
# the theme's black and white, which pick_vivid would drop anyway.
THEME_KEYS = ["accent"] + [f"color{i}" for i in (1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14)]


def theme_colors(theme_dir: Path = THEME_DIR) -> list[str]:
    try:
        text = (theme_dir / "colors.toml").read_text()
    except OSError:
        return []
    found = dict(re.findall(r'^\s*(\w+)\s*=\s*"(#[0-9a-fA-F]{6})"', text, re.M))
    return [found[k] for k in THEME_KEYS if k in found]


def wallpaper_colors(path: Path = WALLPAPER, count: int = 16) -> list[str]:
    """The wallpaper's dominant colours, most common first.

    ImageMagick quantises a 64px thumbnail (~120 ms for a 4K wallpaper). Sixteen
    buckets rather than a handful: a mostly grey photo still has a few small
    patches of real colour, and with too few buckets they are averaged away.
    """
    try:
        target = path.resolve(strict=True)
    except OSError:
        return []
    try:
        out = subprocess.run(
            # Limits first: a wallpaper can be any file the user points
            # the link at, and ImageMagick otherwise decodes whatever it is
            # told, however large.
            ["/usr/bin/magick", "-limit", "memory", "256MiB", "-limit", "map", "512MiB",
             "-limit", "disk", "0", "-limit", "time", "10",
             str(target) + "[0]", "-resize", "64x64", "-colors", str(count),
             "-format", "%c", "histogram:info:-"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = re.findall(r"^\s*(\d+):.*?(#[0-9A-Fa-f]{6})", out, re.M)
    rows.sort(key=lambda r: -int(r[0]))
    return [hexa for _, hexa in rows]
