"""Compact status for the client status bar and an MCP status resource.

The status bar (a Claude Code statusLine command, or any client shelling to
``net-sift status --line``) shows which sources are connected at a glance.
"""

from __future__ import annotations

from .access import opencli
from .engine import sources


def snapshot() -> dict:
    walled = sorted(opencli.walled_sources().keys())
    return {
        "opencli": opencli.available(),
        "walled": walled,
        "keyless_count": len(sources.SOURCES),
    }


def line() -> str:
    s = snapshot()
    oc = "green" if s["opencli"] else "red"
    walled = ",".join(s["walled"]) if s["walled"] else "none"
    dot = "\U0001f7e2" if s["opencli"] else "\U0001f534"
    return f"net-sift {dot} opencli:{oc} | walled:{walled} | keyless:{s['keyless_count']}"
