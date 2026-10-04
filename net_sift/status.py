"""Compact status for the client status bar and an MCP status resource.

The status bar (a Claude Code statusLine command, or any client shelling to
``net-sift status --line``) shows at a glance whether the managed profile is ready
and how many accounts are signed in.
"""

from __future__ import annotations

from . import config
from .access import profile
from .engine import sources


def snapshot() -> dict:
    bid = config.get_browser_choice(config.HOME)
    managed = profile.managed_dir(config.HOME, bid) if bid else None
    ready = bool(managed and managed.is_dir())
    accounts = sorted(s for s, on in profile.logged_in(str(managed)).items() if on) if ready else []
    # keyless engine sources plus the no-account OpenCLI web sources
    from .access import opencli

    web_count = len(sources.SOURCES) + len(opencli.OPEN_SEARCH)
    return {
        "browser": bid,
        "profile_ready": ready,
        "accounts": accounts,
        "web_count": web_count,
    }


def line() -> str:
    """One informative status line with a colored [NET-SIFT] badge. net-sift gets
    its own line (the installer adds it below your existing bar).
    Blue badge when the managed profile is ready, red when not.
    Examples:
      [NET-SIFT] 5 accounts + 24 web sources ready
      [NET-SIFT] no profile - run net-sift install
    """
    s = snapshot()
    color = 33 if s["profile_ready"] else 196  # blue when ready, red when not
    badge = f"\033[1;38;5;{color}m[NET-SIFT]\033[0m"
    if s["profile_ready"]:
        return f"{badge} {len(s['accounts'])} accounts + {s['web_count']} web sources ready"
    return f"{badge} no profile - run net-sift install"
