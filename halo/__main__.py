"""halo: control the lights from a terminal, a hotkey or a hook.

  halo toggle | on | off              every light, or --device ID
  halo bright 60 | +10 | -10
  halo color HUE SAT                  0-359, 0-100
  halo temp KELVIN
  halo theme                          apply the current Omarchy theme now
  halo theme-sync                     the same, only if "follow theme" is on
  halo status                         JSON, one object per light
  halo scan                           TP-Link lights and plugs on this network
  halo daemon                         run the daemon in the foreground
  halo stop                           stop the daemon if it is running

Every command but `daemon` starts the daemon when it is not already running
and leaves it to exit on its own once idle, so a second hotkey press within a
minute skips the two-second handshake.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

from . import store


class Client:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = b""
        self.next_id = 1

    @classmethod
    def connect(cls, start: bool = True, timeout: float = 8.0) -> "Client":
        s = _try_connect()
        if s is None and start:
            _spawn_daemon()
            deadline = time.monotonic() + timeout
            while s is None and time.monotonic() < deadline:
                time.sleep(0.05)
                s = _try_connect()
        if s is None:
            raise SystemExit("halo: the daemon did not start; see " + str(store.CACHE_DIR / "daemon.log"))
        return cls(s)

    def call(self, op: str, timeout: float = 30.0, **params):
        rid = self.next_id
        self.next_id += 1
        self.sock.sendall((json.dumps({"id": rid, "op": op, **params}) + "\n").encode())
        self.sock.settimeout(timeout)
        while True:
            while b"\n" not in self.buf:
                chunk = self.sock.recv(65536)
                if not chunk:
                    raise SystemExit("halo: the daemon closed the connection")
                self.buf += chunk
            line, self.buf = self.buf.split(b"\n", 1)
            msg = json.loads(line)
            if msg.get("id") != rid:
                continue  # an event, or an answer to someone else's question
            if not msg.get("ok"):
                raise SystemExit("halo: " + str(msg.get("error")))
            return msg.get("result")


def _try_connect() -> socket.socket | None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(str(store.SOCKET))
        return s
    except OSError:
        s.close()
        return None


def _spawn_daemon() -> None:
    store.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(store.CACHE_DIR / "daemon.log", "ab")
    # A new session, so the daemon outlives the hotkey or panel that started
    # it and is not killed with that process group.
    subprocess.Popen([sys.executable, "-m", "halo", "daemon"], stdin=subprocess.DEVNULL,
                     stdout=log, stderr=log, start_new_session=True,
                     cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _wait_ready(c: Client, timeout: float = 12.0) -> list[dict]:
    """The devices, once every one of them has connected or failed."""
    deadline = time.monotonic() + timeout
    while True:
        devices = c.call("hello")["devices"]
        if all(d["status"] != "connecting" for d in devices) or time.monotonic() > deadline:
            return devices
        time.sleep(0.1)


def main(argv: list[str]) -> int:
    device = None
    if "--device" in argv:
        i = argv.index("--device")
        device = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i : i + 2]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    cmd, args = argv[0], argv[1:]

    if cmd == "daemon":
        from .daemon import main as daemon_main
        return daemon_main()

    if cmd == "stop":
        c = Client.connect(start=False) if _try_connect() else None
        if c:
            c.call("shutdown")
        return 0

    if cmd == "theme-sync" and not store.load_config()["theme"].get("follow"):
        return 0

    c = Client.connect()
    target = {"device": device} if device else {}

    if cmd == "status":
        print(json.dumps(_wait_ready(c), indent=2))
        return 0
    if cmd == "scan":
        print(json.dumps(c.call("setup.scan", timeout=60), indent=2))
        return 0

    devices = _wait_ready(c)
    if not devices:
        raise SystemExit("halo: no lights set up yet; open the panel to add one")
    down = [d for d in devices if d["status"] != "ready" and (not device or d["id"] == device)]
    if down:
        print("halo: not reachable: " + ", ".join(f"{d['name']} ({d['error']})" for d in down),
              file=sys.stderr)

    if cmd in ("toggle", "on", "off"):
        req = {"toggle": True} if cmd == "toggle" else {"power": cmd == "on"}
        c.call("set", wait=True, **target, **req)
    elif cmd == "bright" and args:
        a = args[0]
        req = {"brightnessDelta": int(a)} if a[0] in "+-" else {"brightness": int(a)}
        c.call("set", wait=True, **target, **req)
    elif cmd == "color" and len(args) == 2:
        c.call("set", wait=True, **target, hs=[int(args[0]), int(args[1])])
    elif cmd == "temp" and args:
        c.call("set", wait=True, **target, temp=int(args[0]))
    elif cmd in ("theme", "theme-sync"):
        c.call("theme.apply", wait=True, **target)
    else:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    return 1 if down else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
