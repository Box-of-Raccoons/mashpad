# mashpad/paths.py — read-only content root + writable data dir resolution.
#
# Pure stdlib — no pygame import (joins the purity test). Centralises every
# filesystem-root decision so the app behaves identically whether it runs from a
# source checkout (dev machine + Raspberry Pi) or inside a frozen PyInstaller
# bundle on Windows.
#
#   app_root()  — read-only content: assets/ (font, splash, images) and sounds/.
#   data_dir()  — writable location for settings.json.
#
# Not frozen (dev + Pi): BOTH are the repo root (parent of the `mashpad` package
# dir), exactly as the code behaved before this module existed — so Linux/Pi
# behaviour is byte-for-byte unchanged. Frozen: app_root is the read-only bundle
# dir and data_dir is %APPDATA%\mashpad, so we never try to write settings next
# to a read-only exe in Program Files.

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_root() -> Path:
    """Read-only content root (holds assets/ and sounds/).

    Frozen (PyInstaller, `sys.frozen` truthy): the bundle dir — `sys._MEIPASS`
    for a one-file build, or the executable's own dir for a one-dir build (where
    `_MEIPASS` is unset). Not frozen: the repo root = parent of the `mashpad`
    package dir (the historical behaviour of audio.repo_root()).
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def source_dir() -> Path:
    """Directory holding the mashpad package .py source (what BabyIDE reads).

    Not frozen (dev + Pi): the `mashpad` package dir itself. Frozen: the
    `mashpad_src` folder the PyInstaller spec bundles under app_root().
    """
    if getattr(sys, "frozen", False):
        return app_root() / "mashpad_src"
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    """Writable directory for settings.json; created if missing.

    Frozen: %APPDATA%\\mashpad (Program Files is read-only for a normal user),
    falling back to ~/mashpad when APPDATA is unset. The directory is created
    (parents + exist_ok) before returning. Not frozen: the same repo root as
    app_root(), which always exists — so dev + Pi keep writing settings.json to
    the repo root exactly as before.
    """
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("APPDATA", Path.home()))
        d = base / "mashpad"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return app_root()
