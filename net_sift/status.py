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
    """One informative status line with a colored [NET-SIFT] badge. net-sift gets
    its own line (the installer adds it below your existing bar).
    Blue badge when a browser is connected, red when not.
    Examples:
      [NET-SIFT] 7 social + 11 web sources ready
      [NET-SIFT] browser not connected · 11 web sources ready
    """
    s = snapshot()
    color = 33 if s["opencli"] else 196  # blue when connected, red when not
    badge = f"\033[1;38;5;{color}m[NET-SIFT]\033[0m"
    if s["opencli"]:
        return f"{badge} {len(s['walled'])} social + {s['keyless_count']} web sources ready"
    return f"{badge} browser not connected · {s['keyless_count']} web sources ready"
