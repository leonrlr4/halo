"""The daemon against a fake light: queueing, coalescing, reconnecting."""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = f"{_tmp}/config"
os.environ["XDG_CACHE_HOME"] = f"{_tmp}/cache"
os.environ["XDG_RUNTIME_DIR"] = f"{_tmp}/run"

from halo import daemon, store  # noqa: E402  -- must see the env above
from halo.adapters.base import Adapter, Caps, LightState  # noqa: E402


class FakeLight(Adapter):
    def __init__(self, segments=50, delay=0.02):
        self.caps = Caps(color=True, temp_range=(2500, 9000), segments=segments, effects=["Aurora"])
        self.state = LightState(on=True, brightness=50)
        self.delay = delay
        self.log = []
        self.fail_connect = 0
        self.connection = {"fake": True}

    async def connect(self):
        if self.fail_connect:
            self.fail_connect -= 1
            raise OSError("unreachable")

    async def close(self):
        pass

    async def _cmd(self, *entry):
        await asyncio.sleep(self.delay)
        self.log.append(entry)

    async def set_power(self, on):
        await self._cmd("power", on)
        self.state.on = on

    async def set_brightness(self, v):
        await self._cmd("brightness", max(1, min(100, v)))
        self.state.brightness = max(1, min(100, v))

    async def set_hs(self, hs):
        await self._cmd("hs", tuple(hs))
        self.state.mode, self.state.hs = "solid", tuple(hs)

    async def set_temp(self, k):
        await self._cmd("temp", k)

    async def set_segments(self, colors):
        await self._cmd("segments", len(colors))
        self.state.mode, self.state.segments = "segments", colors

    async def set_effect(self, name):
        await self._cmd("effect", name)


def fresh_config(n=1):
    store.save_config({"account": "a@b", "devices": [
        {"id": f"d{i}", "host": f"10.0.0.{i}", "model": "L920", "kind": "light"} for i in range(n)]})


class DaemonTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fresh_config(2)
        self.lights = {}

        def make(entry, cfg):
            light = FakeLight()
            self.lights[entry["id"]] = light
            return light

        self.d = daemon.Daemon(make)
        self.d.start_workers()
        await self.settle()

    async def asyncTearDown(self):
        for wid in list(self.d.workers):
            await self.d._stop_worker(wid)

    async def settle(self):
        for _ in range(100):
            await asyncio.sleep(0.01)
            if all(w.status == "ready" and w.idle() for w in self.d.workers.values()):
                return

    async def test_hello_lists_devices(self):
        h = await self.d.handle({"op": "hello"})
        self.assertFalse(h["needsSetup"])
        self.assertEqual([d["id"] for d in h["devices"]], ["d0", "d1"])
        self.assertEqual(h["devices"][0]["caps"]["segments"], 50)

    async def test_slider_drag_coalesces_to_the_last_value(self):
        light = self.lights["d0"]
        for v in range(10, 60):
            await self.d.handle({"op": "set", "device": "d0", "brightness": v})
        await self.d.handle({"op": "set", "device": "d0", "brightness": 77, "wait": True})
        values = [e[1] for e in light.log if e[0] == "brightness"]
        # The first one was already on its way when the rest arrived; after
        # that only the newest value is ever sent.
        self.assertLessEqual(len(values), 2)
        self.assertEqual(values[-1], 77)

    async def test_colour_replaces_a_pending_gradient(self):
        light = self.lights["d0"]
        light.delay = 0.05
        await self.d.handle({"op": "set", "device": "d0", "brightness": 40})  # occupies the light
        await self.d.handle({"op": "set", "device": "d0", "segments": [[0, 100]] * 50})
        await self.d.handle({"op": "set", "device": "d0", "hs": [120, 80], "wait": True})
        kinds = [e[0] for e in light.log]
        self.assertNotIn("segments", kinds)
        self.assertEqual(light.state.hs, (120, 80))

    async def test_no_device_means_every_device(self):
        await self.d.handle({"op": "set", "power": False, "wait": True})
        self.assertFalse(self.lights["d0"].state.on)
        self.assertFalse(self.lights["d1"].state.on)

    async def test_brightness_delta_is_relative_to_each_light(self):
        self.lights["d1"].state.brightness = 90
        await self.d.handle({"op": "set", "brightnessDelta": 20, "wait": True})
        self.assertEqual(self.lights["d0"].state.brightness, 70)
        self.assertEqual(self.lights["d1"].state.brightness, 100)

    async def test_segments_are_resampled_to_the_strip(self):
        await self.d.handle({"op": "set", "device": "d0", "segments": [[0, 100], [120, 100]], "wait": True})
        self.assertEqual(self.lights["d0"].log[-1], ("segments", 50))
        self.assertEqual(self.lights["d0"].state.segments[0], (0, 100))
        self.assertEqual(self.lights["d0"].state.segments[-1], (120, 100))

    async def test_unknown_device_is_an_error(self):
        with self.assertRaises(KeyError):
            await self.d.handle({"op": "set", "device": "nope", "power": True})

    async def test_favourites_round_trip(self):
        await self.d.handle({"op": "favorites.save", "favorite": {"name": "Dusk", "segments": [[10, 90]]}})
        favs = store.load_config()["favorites"]
        self.assertEqual(favs[-1]["name"], "Dusk")
        await self.d.handle({"op": "favorites.delete", "index": len(favs) - 1})
        self.assertEqual(store.load_config()["favorites"], favs[:-1])

    async def test_theme_options_validated(self):
        with self.assertRaises(ValueError):
            await self.d.handle({"op": "theme.options", "options": {"layout": "zigzag"}})
        t = await self.d.handle({"op": "theme.options", "options": {"layout": "mirror", "bogus": 1}})
        self.assertEqual(t["layout"], "mirror")
        self.assertNotIn("bogus", t)


class StaleConfigTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_daemon_never_writes_back_an_old_copy(self):
        # Started with nothing configured...
        store.CONFIG.unlink(missing_ok=True)
        d = daemon.Daemon(lambda e, c: FakeLight())
        d.start_workers()
        # ...then a light is added by someone else, e.g. an older daemon or a
        # restored backup, while this one is running.
        fresh_config(1)
        await d.handle({"op": "theme.options", "options": {"follow": True}})
        await d.handle({"op": "favorites.save", "favorite": {"name": "x", "hs": [1, 2]}})
        cfg = store.load_config()
        self.assertEqual([e["id"] for e in cfg["devices"]], ["d0"])
        self.assertTrue(cfg["theme"]["follow"])


class ReconnectTest(unittest.IsolatedAsyncioTestCase):
    async def test_retries_until_the_light_answers(self):
        fresh_config(1)
        light = FakeLight()
        light.fail_connect = 1
        daemon.RECONNECT_DELAYS = (0.05,)
        d = daemon.Daemon(lambda e, c: light)
        d.start_workers()
        w = d.workers["d0"]
        for _ in range(100):
            await asyncio.sleep(0.01)
            if w.status == "ready":
                break
        self.assertEqual(w.status, "ready")
        await d._stop_worker("d0")


class SocketTest(unittest.IsolatedAsyncioTestCase):
    async def test_request_reply_and_events_over_the_socket(self):
        fresh_config(1)
        d = daemon.Daemon(lambda e, c: FakeLight())
        path = Path(os.environ["XDG_RUNTIME_DIR"]) / "t.sock"
        path.parent.mkdir(parents=True, exist_ok=True)
        server = await asyncio.start_unix_server(d.serve_client, path=str(path))
        d.start_workers()
        r, w = await asyncio.open_unix_connection(str(path))
        w.write(b'{"id": 1, "op": "set", "device": "d0", "hs": [30, 60], "wait": true}\n')
        await w.drain()
        got_reply = got_event = False
        for _ in range(20):
            msg = json.loads(await asyncio.wait_for(r.readline(), 2))
            if msg.get("id") == 1:
                got_reply = msg["ok"]
            if msg.get("event") == "device" and msg["device"]["state"]["hs"] == [30, 60]:
                got_event = True
            if got_reply and got_event:
                break
        self.assertTrue(got_reply)
        self.assertTrue(got_event)
        w.close()
        server.close()
        await d._stop_worker("d0")


if __name__ == "__main__":
    unittest.main()
