"""What the daemon needs from a brand of light, and nothing more.

The panel never learns which brand it is talking to. It reads `caps` and draws
only the controls a light has: no temperature slider for a light without
colour temperature, no gradient editor for a light with one segment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

HS = tuple[int, int]


@dataclass
class Caps:
    color: bool = False
    temp_range: tuple[int, int] | None = None
    # 1 means the whole light is one colour. Anything above that is how many
    # independently coloured stretches it has.
    segments: int = 1
    effects: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"color": self.color, "tempRange": self.temp_range,
                "segments": self.segments, "effects": self.effects}


@dataclass
class LightState:
    on: bool = False
    brightness: int = 100
    # What the light is showing: one colour, white at a temperature, a
    # per-segment pattern, or a built-in effect.
    mode: str = "solid"
    hs: HS = (0, 0)
    temp: int = 0
    segments: list[HS] = field(default_factory=list)
    effect: str | None = None

    def to_json(self) -> dict:
        return {"on": self.on, "brightness": self.brightness, "mode": self.mode,
                "hs": list(self.hs), "temp": self.temp,
                "segments": [list(s) for s in self.segments], "effect": self.effect}


class Adapter:
    """One physical light. Methods raise on failure; the daemon reports it."""

    caps: Caps
    state: LightState

    async def connect(self) -> None: ...
    async def refresh(self) -> LightState: ...
    async def set_power(self, on: bool) -> None: ...
    async def set_brightness(self, value: int) -> None: ...
    async def set_hs(self, hs: HS) -> None: ...
    async def set_temp(self, kelvin: int) -> None: ...
    async def set_segments(self, colors: list[HS]) -> None: ...
    async def set_effect(self, name: str) -> None: ...
    async def close(self) -> None: ...
