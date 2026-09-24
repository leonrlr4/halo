"""Where Halo keeps things, and the one place that reads or writes them.

config.json   devices, theme options, favourites -- no secrets
state.json    last state seen per device, so the panel has something true-ish
              to draw in the two seconds before a light answers
keyring       the TP-Link account password, via secret-tool (libsecret)
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import tempfile
from pathlib import Path

ID = "leonrlr4.halo"

HOME = Path.home()
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / ID
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / ID
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
SOCKET = RUNTIME_DIR / f"{ID}.sock"

CONFIG = CONFIG_DIR / "config.json"
STATE = CACHE_DIR / "state.json"

DEFAULT_THEME = {"follow": False, "source": "theme", "layout": "gradient", "vivid": True}


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data, mode: int = 0o644) -> None:
    # Write-then-rename: a crash mid-write must not leave a truncated config
    # that the next start reads as "no devices".
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_config() -> dict:
    cfg = _read_json(CONFIG, {})
    cfg.setdefault("devices", [])
    cfg.setdefault("account", "")
    cfg["theme"] = {**DEFAULT_THEME, **cfg.get("theme", {})}
    cfg.setdefault("favorites", [])
    return cfg


def save_config(cfg: dict) -> None:
    _write_json(CONFIG, cfg)


def update_config(change) -> dict:
    """Apply `change` to the config as it is on disk now, and save it.

    Every write goes through here, never through a copy held in memory: a
    daemon that loaded the file a minute ago would otherwise write that old
    copy back and silently drop a light added since. The lock covers the
    read and the write, so two processes cannot interleave them.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_DIR / ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cfg = load_config()
        change(cfg)
        save_config(cfg)
        return cfg


def load_state() -> dict:
    return _read_json(STATE, {})


def save_state(state: dict) -> None:
    _write_json(STATE, state)


# ---- keyring ---------------------------------------------------------------

_ATTRS = ["service", ID, "kind", "tplink"]
# By absolute path: the daemon may have been started from anywhere.
SECRET_TOOL = "/usr/bin/secret-tool"


def get_password(account: str) -> str | None:
    if not account:
        return None
    try:
        r = subprocess.run([SECRET_TOOL, "lookup", *_ATTRS, "account", account],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 and r.stdout else None


def set_password(account: str, password: str) -> None:
    # The password goes in on stdin, never argv: argv is readable by every
    # process on the machine through /proc.
    subprocess.run([SECRET_TOOL, "store", "--label", "Halo: TP-Link account",
                    *_ATTRS, "account", account],
                   input=password, text=True, timeout=30, check=True)
