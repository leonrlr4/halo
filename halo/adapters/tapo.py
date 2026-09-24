"""TP-Link Tapo and Kasa, through python-kasa.

Newer Tapo firmware (L920 1.4.x, P110 1.4.x and others) speaks TPAP, which no
released python-kasa understands yet; scripts/setup installs the branch from
python-kasa PR #1592 for that reason. Nothing in this file depends on which
build is installed.

Measured on an L920-5 (EU), firmware 1.4.4, over Wi-Fi:
  handshake + first read     ~2.0 s   -- why the daemon holds the connection
  one colour change          ~110 ms  -- sustained ~9/s, no errors in 80
  all 50 segments at once    ~150 ms  -- sustained ~6.7/s
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import subprocess
import uuid

from kasa import Credentials, Device, DeviceConfig, Discover, Module

from .base import HS, Adapter, Caps, LightState

# Device types worth showing. Cameras, hubs and robot vacuums answer discovery
# too; none of them is a light.
KINDS = {
    "SMART.TAPOBULB": "light",
    "IOT.SMARTBULB": "light",
    "SMART.KASABULB": "light",
    "SMART.TAPOPLUG": "plug",
    "SMART.KASAPLUG": "plug",
    "IOT.SMARTPLUGSWITCH": "plug",
    "SMART.KASASWITCH": "plug",
    "SMART.TAPOSWITCH": "plug",
}

# The segment rule id is stored on the light and shown in the Tapo app's
# history; a fixed one means repeated edits replace a single entry instead of
# accumulating one per change.
RULE_ID = "halo"


class TapoAdapter(Adapter):
    def __init__(self, host: str, credentials: Credentials, connection: dict | None = None):
        self.host = host
        self.credentials = credentials
        self.connection = connection
        self.dev: Device | None = None
        self.alias: str | None = None
        self.caps = Caps()
        self.state = LightState()

    # ---- connection ----------------------------------------------------------

    async def connect(self) -> None:
        dev = None
        if self.connection:
            # Skips discovery: straight to the handshake with the transport
            # we found last time. Falls back below if the light moved or
            # changed firmware.
            try:
                cfg = DeviceConfig.from_dict({"host": self.host, "connection_type": self.connection})
                cfg.credentials = self.credentials
                dev = await Device.connect(config=cfg)
            except Exception:
                dev = None
        if dev is None:
            dev = await Discover.discover_single(self.host, credentials=self.credentials,
                                                 discovery_timeout=3)
            await dev.update()
        self.dev = dev
        self.alias = dev.alias
        self.connection = dev.config.to_dict().get("connection_type")
        self.caps = await self._read_caps()
        await self.refresh()

    async def _read_caps(self) -> Caps:
        dev = self.dev
        caps = Caps()
        if Module.Light not in dev.modules:
            return caps
        light = dev.modules[Module.Light]
        caps.color = Module.Color in dev.modules
        if Module.ColorTemperature in dev.modules:
            r = light.valid_temperature_range
            caps.temp_range = (r.min, r.max)
        components = getattr(dev, "_components", {}) or {}
        if "segment" in components and "segment_effect" in components:
            try:
                r = await dev.protocol.query("get_device_segment")
                caps.segments = int(r["get_device_segment"]["segment"])
            except Exception:
                caps.segments = 1
        if Module.LightEffect in dev.modules:
            fx = dev.modules[Module.LightEffect]
            caps.effects = [e for e in fx.effect_list if e != fx.LIGHT_EFFECTS_OFF]
        return caps

    async def close(self) -> None:
        if self.dev is not None:
            try:
                await self.dev.disconnect()
            except Exception:
                pass
            self.dev = None

    # ---- state ---------------------------------------------------------------

    async def refresh(self) -> LightState:
        dev = self.dev
        await dev.update()
        st = LightState(on=dev.is_on)
        if Module.Light in dev.modules:
            light = dev.modules[Module.Light]
            st.brightness = light.brightness if light.is_dimmable else 100
            if self.caps.color:
                h, s, _ = light.hsv
                st.hs = (h, s)
            if self.caps.temp_range:
                st.temp = light.color_temp
            st.mode = "temp" if st.temp else "solid"
            if Module.LightEffect in dev.modules:
                fx = dev.modules[Module.LightEffect]
                if fx.effect and fx.effect != fx.LIGHT_EFFECTS_OFF:
                    st.mode, st.effect = "effect", fx.effect
            if self.caps.segments > 1 and st.mode != "effect":
                rule = (await dev.protocol.query("get_segment_effect_rule"))["get_segment_effect_rule"]
                states = rule.get("states") or []
                if rule.get("enable") and states:
                    st.mode = "segments"
                    st.segments = [(int(c[0]), int(c[1])) for c in states]
                    st.brightness = int(rule.get("brightness", st.brightness))
        self.state = st
        return st

    # ---- commands ------------------------------------------------------------

    async def set_power(self, on: bool) -> None:
        await (self.dev.turn_on() if on else self.dev.turn_off())
        self.state.on = on

    async def set_brightness(self, value: int) -> None:
        value = max(1, min(100, int(value)))
        if self.state.mode == "segments" and self.state.segments:
            # Plain set_brightness switches a segment rule off and leaves the
            # strip one colour. The rule carries its own brightness, so the
            # pattern has to be sent again with the new one.
            self.state.brightness = value
            await self._apply_rule(self.state.segments)
        else:
            await self.dev.modules[Module.Light].set_brightness(value)
            self.state.brightness = value
        self.state.on = True

    async def set_hs(self, hs: HS) -> None:
        h, s = int(hs[0]) % 360, max(0, min(100, int(hs[1])))
        await self.dev.modules[Module.Light].set_hsv(h, s, self.state.brightness)
        self.state.mode, self.state.hs, self.state.temp, self.state.effect = "solid", (h, s), 0, None
        self.state.on = True

    async def set_temp(self, kelvin: int) -> None:
        lo, hi = self.caps.temp_range or (2500, 6500)
        k = max(lo, min(hi, int(kelvin)))
        await self.dev.modules[Module.Light].set_color_temp(k)
        self.state.mode, self.state.temp, self.state.effect = "temp", k, None
        self.state.on = True

    async def set_segments(self, colors: list[HS]) -> None:
        n = self.caps.segments
        if n <= 1:
            raise ValueError("this light has no segments")
        if len(colors) != n:
            raise ValueError(f"expected {n} colours, got {len(colors)}")
        colors = [(int(h) % 360, max(0, min(100, int(s)))) for h, s in colors]
        if not self.state.on:
            await self.dev.turn_on()
        await self._apply_rule(colors)
        self.state.mode, self.state.segments, self.state.effect = "segments", colors, None
        self.state.on = True

    async def _apply_rule(self, colors: list[HS]) -> None:
        states = [[h, s, 100, 0] for h, s in colors]
        # display_colors is what the Tapo app draws on its thumbnail; a few
        # samples along the strip is what the app itself sends.
        step = max(1, len(states) // 4)
        rule = {
            "brightness": self.state.brightness, "custom": 1, "deviceType": "strip",
            "display_colors": states[::step][:4], "enable": 1, "id": RULE_ID, "name": "Halo",
            "segments": list(range(len(states))), "states": states, "type": "none",
        }
        await self.dev.protocol.query({"apply_segment_effect_rule": rule})

    async def set_effect(self, name: str) -> None:
        fx = self.dev.modules[Module.LightEffect]
        await fx.set_effect(name)
        off = name == fx.LIGHT_EFFECTS_OFF
        self.state.mode, self.state.effect = ("solid", None) if off else ("effect", name)
        self.state.on = True


# ---- finding lights ----------------------------------------------------------

def _local_networks() -> list[ipaddress.IPv4Network]:
    try:
        out = subprocess.run(["ip", "-4", "-j", "addr", "show", "scope", "global"],
                             capture_output=True, text=True, timeout=5).stdout
        addrs = json.loads(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    nets = []
    for iface in addrs:
        name = iface.get("ifname", "")
        # Container bridges have no lights on them, and a /16 docker network
        # would be 65 000 probes.
        if name.startswith(("docker", "br-", "veth", "virbr", "podman", "tailscale", "wg")):
            continue
        for a in iface.get("addr_info", []):
            net = ipaddress.ip_network(f"{a['local']}/{a['prefixlen']}", strict=False)
            if net.num_addresses <= 1024:
                nets.append(net)
    return nets


async def scan(credentials: Credentials | None, timeout: float = 3.0) -> list[dict]:
    """Every TP-Link light and plug that answers on the local networks.

    Broadcast discovery found nothing on the machine this was written on
    (Omarchy, ufw active), while a unicast probe of the same light answered.
    The likely cause is the firewall dropping replies that come from an
    address other than the one probed. So this does both and merges them.
    """
    found: dict[str, dict] = {}

    def record(dev: Device) -> None:
        info = getattr(dev, "_discovery_info", None) or {}
        kind = KINDS.get(info.get("device_type") or info.get("mic_type") or "", None)
        if kind is None and dev.device_type is not None:
            kind = "light" if "bulb" in str(dev.device_type).lower() else None
        if kind is None:
            return
        found[dev.host] = {
            "host": dev.host,
            "model": info.get("device_model") or dev.model,
            "kind": kind,
            "id": info.get("device_id") or dev.device_id,
            "mac": info.get("mac") or "",
        }

    async def broadcast() -> None:
        try:
            for dev in (await Discover.discover(credentials=credentials,
                                                discovery_timeout=timeout)).values():
                record(dev)
        except Exception:
            pass

    # Every probe spends most of its time waiting out the timeout, so a /24
    # goes in one wave: 254 sockets for three seconds, not four waves of 64.
    sem = asyncio.Semaphore(256)

    async def probe(host: str) -> None:
        if host in found:
            return
        async with sem:
            try:
                dev = await Discover.discover_single(host, credentials=credentials,
                                                     discovery_timeout=timeout)
            except Exception:
                return
            record(dev)

    hosts = [str(h) for net in _local_networks() for h in net.hosts()]
    await asyncio.gather(broadcast(), *(probe(h) for h in hosts))
    return sorted(found.values(), key=lambda d: tuple(int(x) for x in d["host"].split(".")))


def new_id() -> str:
    return uuid.uuid4().hex[:12]
