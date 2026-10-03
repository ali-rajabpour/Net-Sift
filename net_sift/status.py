"""Compact status for the client status bar and an MCP status resource.

The status bar (a Claude Code statusLine command, or any client shelling to
``net-sift status --line``) shows which sources are connected at a glance.
"""

from __future__ import annotations

from .access import opencli
from .engine import sources


def snapshot() -> dict:
    # Cached: the status bar refreshes often and a live `opencli doctor` takes
    # several seconds. Walled set is shown as the supported platforms when a
    # browser session is connected; `net-sift doctor` enumerates the live adapters.
    connected = opencli.available_cached()
    return {
        "opencli": connected,
        "walled": sorted(opencli.WALLED_SITES) if connected else [],
        "keyless_count": len(sources.SOURCES),
    }


def line() -> str:
    s = snapshot()
    walled = ",".join(s["walled"]) if s["walled"] else "none"
    dot = "\U0001f7e2" if s["opencli"] else "\U0001f534"
    return f"net-sift {dot} accounts:{walled} | keyless:{s['keyless_count']}"
