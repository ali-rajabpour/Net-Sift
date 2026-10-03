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
    """One informative status line. net-sift gets its own line (the installer adds
    it below your existing bar), so it can spell things out.
    Examples:
      net-sift ● 7 social + 11 web sources ready
      net-sift ○ browser not connected · 11 web sources ready
    """
    s = snapshot()
    if s["opencli"]:
        return f"net-sift ● {len(s['walled'])} social + {s['keyless_count']} web sources ready"
    return f"net-sift ○ browser not connected · {s['keyless_count']} web sources ready"
