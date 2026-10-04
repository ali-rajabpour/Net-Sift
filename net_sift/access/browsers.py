"""Discover installed Chromium browsers on macOS: executable and source profile dir.

macOS only for now; Windows and Linux maps come later. A browser counts as usable
only when its executable and a ``Default`` profile both exist.
"""

from __future__ import annotations

import os
from pathlib import Path

_SUPPORT = Path.home() / "Library" / "Application Support"
_APPS = Path("/Applications")

# id -> (display name, executable path, source user-data-dir)
MAC_BROWSERS: dict[str, tuple[str, str, str]] = {
    "chrome": (
        "Google Chrome",
        str(_APPS / "Google Chrome.app/Contents/MacOS/Google Chrome"),
        str(_SUPPORT / "Google/Chrome"),
    ),
    "comet": (
        "Comet",
        str(_APPS / "Comet.app/Contents/MacOS/Comet"),
        str(_SUPPORT / "Comet"),
    ),
    "brave": (
        "Brave",
        str(_APPS / "Brave Browser.app/Contents/MacOS/Brave Browser"),
        str(_SUPPORT / "BraveSoftware/Brave-Browser"),
    ),
    "edge": (
        "Microsoft Edge",
        str(_APPS / "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        str(_SUPPORT / "Microsoft Edge"),
    ),
    "arc": (
        "Arc",
        str(_APPS / "Arc.app/Contents/MacOS/Arc"),
        str(_SUPPORT / "Arc/User Data"),
    ),
    "vivaldi": (
        "Vivaldi",
        str(_APPS / "Vivaldi.app/Contents/MacOS/Vivaldi"),
        str(_SUPPORT / "Vivaldi"),
    ),
    "chromium": (
        "Chromium",
        str(_APPS / "Chromium.app/Contents/MacOS/Chromium"),
        str(_SUPPORT / "Chromium"),
    ),
}


def detect() -> dict[str, dict]:
    """Browsers present on this machine, keyed by id."""
    out: dict[str, dict] = {}
    for bid, (name, exe, prof) in MAC_BROWSERS.items():
        if os.path.exists(exe) and os.path.isdir(os.path.join(prof, "Default")):
            out[bid] = {"id": bid, "name": name, "executable": exe, "source_profile": prof}
    return out
