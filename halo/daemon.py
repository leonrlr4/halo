"""The one process that talks to the lights.

A light allows one session at a time in practice, and opening one costs a
two-second handshake. So a single daemon holds every connection, and the
panel, the hotkeys and the theme hook all send it requests over a unix
socket. It is started on demand and exits after IDLE_EXIT seconds with no
client attached and nothing left to send: nothing of Halo runs while nobody
is using it.

Wire format: one JSON object per line each way.
  request   {"id": 7, "op": "set", ...}
  reply     {"id": 7, "ok": true, "result": ...}  or  {"id": 7, "ok": false, "error": "..."}
  event     {"event": "device", "device": {...}}  -- pushed to every client
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import signal
import sys
import time
from collections import OrderedDict
from typing import Awaitable, Callable

from . import palette, store
from .adapters.base import Adapter

IDLE_EXIT = 60.0
RECONNECT_DELAYS = (1, 2, 5, 10, 30)

Job = Callable[[Adapter], Awaitable[None]]


class Worker:
    """One light: its adapter, its connection, and its queue.

    The queue is latest-wins per key. Dragging a slider sends a request for
    every pixel of movement, far faster than the ~110 ms a light takes per
    command; replacing the pending one means the light always goes straight
    to where the slider is now instead of replaying where it has been.
    """

    def __init__(self, entry: dict, adapter: Adapter, notify: Callable[["Worker"], None]):
        self.entry = entry
        self.adapter = adapter
        self.notify = notify
        self.status = "connecting"
        self.error = ""
        self.pending: OrderedDict[str, tuple[Job, list[asyncio.Future]]] = OrderedDict()
        self.wake = asyncio.Event()
        self.busy = False
        self.config_dirty = False
        self.task: asyncio.Task | None = None

    @property
    def id(self) -> str:
        return self.entry["id"]

    def idle(self) -> bool:
        return not self.pending and not self.busy

    def to_json(self) -> dict:
        return {
            "id": self.id, "name": self.entry.get("name") or self.entry.get("model") or self.id,
            "model": self.entry.get("model", ""), "kind": self.entry.get("kind", "light"),
            "host": self.entry.get("host", ""), "status": self.status, "error": self.error,
            "caps": self.adapter.caps.to_json(), "state": self.adapter.state.to_json(),
        }

    def submit(self, key: str, job: Job) -> asyncio.Future:
        fut = asyncio.get_running_loop().create_future()
        waiters = [fut]
        if key in self.pending:
            # Whoever was waiting on the replaced job is answered when its
            # replacement runs: from their side the light did end up where
            # they asked, or somewhere newer.
            waiters = self.pending.pop(key)[1] + waiters
        self.pending[key] = (job, waiters)
        self.wake.set()
        return fut

    async def run(self) -> None:
        attempt = 0
        while True:
            if self.status != "ready":
                try:
                    self.status, self.error = "connecting", ""
                    self.notify(self)
                    await self.adapter.connect()
                    self.status, attempt = "ready", 0
                    # The name given in the Tapo app, unless it was renamed here.
                    alias = getattr(self.adapter, "alias", None)
                    if alias and not self.entry.get("renamed") and alias != self.entry.get("name"):
                        self.entry["name"] = alias
                        self.config_dirty = True
                    conn = getattr(self.adapter, "connection", None)
                    if conn and conn != self.entry.get("connection"):
                        self.entry["connection"] = conn
                        self.config_dirty = True
                    self.notify(self)
                except Exception as e:  # noqa: BLE001 -- any failure means "try again later"
                    self.status, self.error = "error", _describe(e)
                    self._fail_pending(self.error)
                    self.notify(self)
                    await asyncio.sleep(RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)])
                    attempt += 1
                    continue
            await self.wake.wait()
            self.wake.clear()
            while self.pending:
                key, (job, waiters) = self.pending.popitem(last=False)
                self.busy = True
                try:
                    await job(self.adapter)
                    self.error = ""
                    for w in waiters:
                        if not w.done():
                            w.set_result(None)
                except Exception as e:  # noqa: BLE001
                    self.error = _describe(e)
                    for w in waiters:
                        if not w.done():
                            w.set_exception(RuntimeError(self.error))
                    if _is_connection_error(e):
                        self.status = "error"
                        await self.adapter.close()
                        self.notify(self)
                        break
                finally:
                    self.busy = False
                self.notify(self)

    def _fail_pending(self, msg: str) -> None:
        while self.pending:
            _, (_, waiters) = self.pending.popitem(last=False)
            for w in waiters:
                if not w.done():
                    w.set_exception(RuntimeError(msg))


def _describe(e: Exception) -> str:
    text = str(e) or type(e).__name__
    return text.splitlines()[0][:200]


def _is_connection_error(e: Exception) -> bool:
    """Whether the session is gone, as opposed to one command being refused.

    Matched by class name so this module does not import python-kasa, which
    keeps it testable with a fake adapter.
    """
    names = {c.__name__ for c in type(e).__mro__}
    return bool(names & {"_ConnectionError", "_RetryableError", "AuthenticationError",
                         "TimeoutError", "OSError"})


# ---- the daemon --------------------------------------------------------------

class Daemon:
    def __init__(self, make_adapter: Callable[[dict, dict], Adapter]):
        self.make_adapter = make_adapter
        self.cfg = store.load_config()
        self.workers: dict[str, Worker] = {}
        self.clients: set[asyncio.StreamWriter] = set()
        self.last_activity = time.monotonic()
        self.stop = asyncio.Event()
        self._state_dirty = False

    # ---- workers -------------------------------------------------------------

    def start_workers(self) -> None:
        for entry in self.cfg["devices"]:
            self._start(dict(entry))

    def _start(self, entry: dict) -> Worker:
        adapter = self.make_adapter(entry, self.cfg)
        cached = store.load_state().get(entry["id"])
        if cached:
            _restore_state(adapter, cached)
        w = Worker(entry, adapter, self._on_change)
        w.task = asyncio.get_running_loop().create_task(w.run())
        self.workers[w.id] = w
        return w

    async def _stop_worker(self, wid: str) -> None:
        w = self.workers.pop(wid, None)
        if w and w.task:
            w.task.cancel()
            await w.adapter.close()

    def _on_change(self, w: Worker) -> None:
        self.last_activity = time.monotonic()
        self._state_dirty = True
        self.broadcast({"event": "device", "device": w.to_json()})

    def _patch_device(self, wid: str, fields: dict) -> None:
        def change(cfg):
            for e in cfg["devices"]:
                if e["id"] == wid:
                    e.update(fields)
        self.cfg = store.update_config(change)

    def _persist(self) -> None:
        if not self._state_dirty:
            return
        self._state_dirty = False
        store.save_state({wid: {"caps": w.adapter.caps.to_json(), "state": w.adapter.state.to_json()}
                          for wid, w in self.workers.items() if w.status == "ready"})
        # The connection details learnt on a handshake make the next start
        # skip discovery; they live with the device entry.
        for w in self.workers.values():
            if w.config_dirty:
                w.config_dirty = False
                self._patch_device(w.id, {k: w.entry[k] for k in ("name", "connection") if k in w.entry})

    # ---- clients -------------------------------------------------------------

    def broadcast(self, msg: dict) -> None:
        line = (json.dumps(msg) + "\n").encode()
        for w in list(self.clients):
            try:
                w.write(line)
            except Exception:  # noqa: BLE001
                self.clients.discard(w)

    async def serve_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.clients.add(writer)
        self.last_activity = time.monotonic()
        try:
            while line := await reader.readline():
                try:
                    req = json.loads(line)
                except ValueError:
                    continue
                asyncio.get_running_loop().create_task(self._answer(req, writer))
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self.clients.discard(writer)
            self.last_activity = time.monotonic()
            writer.close()

    async def _answer(self, req: dict, writer: asyncio.StreamWriter) -> None:
        rid = req.get("id")
        try:
            result = await self.handle(req)
            reply = {"id": rid, "ok": True, "result": result}
        except Exception as e:  # noqa: BLE001
            reply = {"id": rid, "ok": False, "error": _describe(e)}
        if rid is None:
            return
        try:
            writer.write((json.dumps(reply) + "\n").encode())
            await writer.drain()
        except Exception:  # noqa: BLE001
            pass

    # ---- requests ------------------------------------------------------------

    def _targets(self, req: dict) -> list[Worker]:
        dev = req.get("device")
        if dev in (None, "", "all"):
            return list(self.workers.values())
        if dev not in self.workers:
            raise KeyError(f"no device {dev!r}")
        return [self.workers[dev]]

    def hello(self) -> dict:
        return {
            "account": self.cfg["account"],
            "needsSetup": not self.cfg["account"] or not self.cfg["devices"],
            "devices": [w.to_json() for w in self.workers.values()],
            "theme": self.cfg["theme"],
            "favorites": self.cfg["favorites"],
        }

    async def handle(self, req: dict):
        op = req.get("op")
        self.last_activity = time.monotonic()

        if op == "hello":
            return self.hello()

        if op == "set":
            futs = []
            for w in self._targets(req):
                futs += _set_jobs(w, req)
            if req.get("wait"):
                await asyncio.gather(*futs)
            else:
                for f in futs:
                    f.add_done_callback(_swallow)
            return None

        if op == "palette":
            return {"theme": palette.theme_colors(), "wallpaper": palette.wallpaper_colors()}

        if op == "theme.options":
            patch = {k: v for k, v in (req.get("options") or {}).items() if k in store.DEFAULT_THEME}
            if "layout" in patch and patch["layout"] not in palette.LAYOUTS:
                raise ValueError(f"unknown layout {patch['layout']!r}")
            if "source" in patch and patch["source"] not in ("theme", "wallpaper"):
                raise ValueError(f"unknown source {patch['source']!r}")
            self.cfg = store.update_config(lambda c: c["theme"].update(patch))
            self.broadcast({"event": "theme", "theme": self.cfg["theme"]})
            return self.cfg["theme"]

        if op == "theme.preview":
            opts = {**self.cfg["theme"], **(req.get("options") or {})}
            colors = theme_source(opts)
            n = int(req.get("segments", 50))
            return {"colors": [palette.hs_to_hex(c) for c in colors],
                    "segments": [palette.hs_to_hex(c) for c in palette.layout(colors, n, opts["layout"])]
                    if colors else []}

        if op == "theme.apply":
            opts = {**self.cfg["theme"], **(req.get("options") or {})}
            colors = theme_source(opts)
            if not colors:
                raise ValueError(f"the current {opts['source']} has no colour a light can show")
            futs = []
            for w in self._targets(req):
                caps = w.adapter.caps
                if caps.segments > 1:
                    segs = palette.layout(colors, caps.segments, opts["layout"])
                    futs.append(w.submit("content", lambda a, s=segs: a.set_segments(s)))
                elif caps.color:
                    futs.append(w.submit("content", lambda a, c=colors[0]: a.set_hs(c)))
            if req.get("wait"):
                await asyncio.gather(*futs)
            else:
                for f in futs:
                    f.add_done_callback(_swallow)
            return {"colors": [palette.hs_to_hex(c) for c in colors]}

        if op == "favorites.save":
            fav = req.get("favorite") or {}
            if not isinstance(fav.get("segments"), list) and not isinstance(fav.get("hs"), list):
                raise ValueError("a favourite needs segments or hs")
            fav = {"name": str(fav.get("name") or "Favourite")[:40],
                   **({"segments": fav["segments"]} if "segments" in fav else {"hs": fav["hs"]})}
            # The editor's stops, when there are any, so a saved gradient can
            # be opened and changed again rather than only replayed.
            if isinstance(fav_in := req.get("favorite", {}).get("stops"), list):
                fav["stops"] = fav_in
            def add_fav(c):
                c["favorites"] = (c["favorites"] + [fav])[-24:]
            self.cfg = store.update_config(add_fav)
            self.broadcast({"event": "favorites", "favorites": self.cfg["favorites"]})
            return self.cfg["favorites"]

        if op == "favorites.delete":
            i = int(req.get("index", -1))
            def del_fav(c):
                if 0 <= i < len(c["favorites"]):
                    del c["favorites"][i]
            self.cfg = store.update_config(del_fav)
            self.broadcast({"event": "favorites", "favorites": self.cfg["favorites"]})
            return self.cfg["favorites"]

        if op == "setup.login":
            account = str(req.get("account") or "").strip()
            password = str(req.get("password") or "")
            if not account or not password:
                raise ValueError("both the email and the password are needed")
            await asyncio.to_thread(store.set_password, account, password)
            self.cfg = store.update_config(lambda c: c.update(account=account))
            # Workers built with the old credentials would keep failing.
            for wid in list(self.workers):
                entry = self.workers[wid].entry
                await self._stop_worker(wid)
                self._start(entry)
            return self.hello()

        if op == "setup.scan":
            from .adapters import tapo
            return await tapo.scan(credentials_for(self.cfg))

        if op == "setup.add":
            host = str(req.get("host") or "")
            if not host:
                raise ValueError("no host")
            if any(e["host"] == host for e in store.load_config()["devices"]):
                raise ValueError(f"{host} is already added")
            from .adapters import tapo
            entry = {"id": tapo.new_id(), "brand": "tapo", "host": host,
                     "model": str(req.get("model") or ""), "kind": str(req.get("kind") or "light"),
                     "name": str(req.get("name") or req.get("model") or host)}
            self.cfg = store.update_config(lambda c: c["devices"].append(entry))
            w = self._start(dict(entry))
            return w.to_json()

        if op == "setup.remove":
            wid = str(req.get("device") or "")
            await self._stop_worker(wid)
            def drop(c):
                c["devices"] = [e for e in c["devices"] if e["id"] != wid]
            self.cfg = store.update_config(drop)
            return self.hello()

        if op == "rename":
            w = self._targets(req)[0]
            w.entry["name"] = str(req.get("name") or "")[:40] or w.entry.get("model", "")
            w.entry["renamed"] = True
            self._patch_device(w.id, {"name": w.entry["name"], "renamed": True})
            self._on_change(w)
            return w.to_json()

        if op == "shutdown":
            self.stop.set()
            return None

        raise ValueError(f"unknown op {op!r}")

    # ---- lifetime ------------------------------------------------------------

    async def watch_idle(self) -> None:
        while not self.stop.is_set():
            await asyncio.sleep(2)
            self._persist()
            busy = any(not w.idle() for w in self.workers.values())
            if self.clients or busy:
                self.last_activity = time.monotonic()
            elif time.monotonic() - self.last_activity > IDLE_EXIT:
                self.stop.set()


def _swallow(fut: asyncio.Future) -> None:
    if not fut.cancelled():
        fut.exception()


def _set_jobs(w: Worker, req: dict) -> list[asyncio.Future]:
    """Turn one `set` request into queued jobs on one light."""
    futs = []
    caps = w.adapter.caps
    if "toggle" in req:
        futs.append(w.submit("power", lambda a: a.set_power(not a.state.on)))
    if "power" in req:
        on = bool(req["power"])
        futs.append(w.submit("power", lambda a: a.set_power(on)))
    if "brightness" in req:
        v = int(req["brightness"])
        futs.append(w.submit("brightness", lambda a: a.set_brightness(v)))
    if "brightnessDelta" in req:
        d = int(req["brightnessDelta"])
        futs.append(w.submit("brightness", lambda a: a.set_brightness(a.state.brightness + d)))
    # Everything below replaces what the light shows, so they share a key: a
    # colour picked after a gradient wins over it, and the other way round.
    if "hs" in req and caps.color:
        hs = tuple(req["hs"])
        futs.append(w.submit("content", lambda a: a.set_hs(hs)))
    if "temp" in req and caps.temp_range:
        k = int(req["temp"])
        futs.append(w.submit("content", lambda a: a.set_temp(k)))
    if "segments" in req and caps.segments > 1:
        segs = [tuple(c) for c in req["segments"]]
        if len(segs) != caps.segments:
            # The panel draws its editor at a fixed resolution; resample so a
            # favourite saved on one strip plays on another of any length.
            segs = [segs[min(len(segs) - 1, i * len(segs) // caps.segments)] for i in range(caps.segments)]
        futs.append(w.submit("content", lambda a: a.set_segments(segs)))
    if "effect" in req and caps.effects:
        name = str(req["effect"])
        futs.append(w.submit("content", lambda a: a.set_effect(name)))
    return futs


def theme_source(opts: dict) -> list[palette.HS]:
    raw = palette.wallpaper_colors() if opts.get("source") == "wallpaper" else palette.theme_colors()
    colors = palette.walk_hues(palette.pick_vivid(raw))
    if opts.get("vivid", True):
        colors = [palette.vivid(c) for c in colors]
    return colors


def credentials_for(cfg: dict):
    from kasa import Credentials
    account = cfg.get("account") or ""
    password = store.get_password(account)
    if not account or password is None:
        return None
    return Credentials(account, password)


def _restore_state(adapter: Adapter, cached: dict) -> None:
    from .adapters.base import Caps, LightState
    c, s = cached.get("caps") or {}, cached.get("state") or {}
    adapter.caps = Caps(color=c.get("color", False),
                        temp_range=tuple(c["tempRange"]) if c.get("tempRange") else None,
                        segments=c.get("segments", 1), effects=c.get("effects", []))
    adapter.state = LightState(on=s.get("on", False), brightness=s.get("brightness", 100),
                               mode=s.get("mode", "solid"), hs=tuple(s.get("hs", (0, 0))),
                               temp=s.get("temp", 0),
                               segments=[tuple(x) for x in s.get("segments", [])],
                               effect=s.get("effect"))


def default_adapter(entry: dict, cfg: dict) -> Adapter:
    from .adapters.tapo import TapoAdapter
    creds = credentials_for(cfg)
    if creds is None:
        from kasa import Credentials
        creds = Credentials("", "")
    return TapoAdapter(entry["host"], creds, entry.get("connection"))


async def serve(make_adapter=default_adapter) -> int:
    store.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    # The lock, not the socket file, decides who runs: two daemons started in
    # the same instant would both see no socket and both bind.
    lock = open(store.RUNTIME_DIR / f"{store.ID}.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    store.SOCKET.unlink(missing_ok=True)
    d = Daemon(make_adapter)
    server = await asyncio.start_unix_server(d.serve_client, path=str(store.SOCKET))
    os.chmod(store.SOCKET, 0o600)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, d.stop.set)
    d.start_workers()
    idle = loop.create_task(d.watch_idle())
    await d.stop.wait()
    idle.cancel()
    server.close()
    store.SOCKET.unlink(missing_ok=True)
    d._state_dirty = True
    d._persist()
    for wid in list(d.workers):
        await d._stop_worker(wid)
    lock.close()
    return 0


def main() -> int:
    return asyncio.run(serve())


if __name__ == "__main__":
    sys.exit(main())
