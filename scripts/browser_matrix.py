#!/usr/bin/env python3
"""Manual integration check for the managed-browser access path. NOT run in CI.

Needs a real, logged-in managed profile created by `net-sift install`. It launches
that browser headless, runs each browser-backed source once, prints OK or the error
code, and asserts the browser process is gone afterward.

Usage:
    python scripts/browser_matrix.py            # uses the wizard's saved browser
    NET_SIFT_BROWSER=comet python scripts/browser_matrix.py
"""

from __future__ import annotations

import sys

from net_sift import config
from net_sift.access import browser, browsers, opencli, profile

EN = "bitcoin etf"
ZH = "人工智能"


def main() -> int:
    import os

    bid = os.environ.get("NET_SIFT_BROWSER") or config.get_browser_choice(config.HOME)
    if not bid:
        print("No browser chosen. Run `net-sift install` first.")
        return 1
    found = browsers.detect().get(bid)
    if not found:
        print(f"Browser {bid} not found on this machine.")
        return 1
    pdir = profile.managed_dir(config.HOME, bid)
    if not pdir.is_dir():
        print(f"No managed profile at {pdir}. Run `net-sift install`.")
        return 1

    # Build each source the way a real sweep does (make_source carries the transient
    # retry), so the matrix reflects production behavior, not a single raw call.
    checks = [
        (name, opencli.make_source(site, cmd, name, cap), ZH if name in ("weixin", "tieba") else EN)
        for name, (site, cmd, cap, _) in opencli.OPEN_SEARCH.items()
    ]
    checks += [
        (
            s,
            opencli.make_source(s, "search"),
            ZH if s in ("bilibili", "xiaohongshu", "zhihu") else EN,
        )
        for s in opencli.WALLED_SITES
    ]

    failures = 0
    with browser.managed_browser(found["executable"], str(pdir)) as endpoint:
        opencli.set_endpoint(endpoint)
        try:
            for name, source, q in checks:
                try:
                    recs, _ = source(q, None, None, 5)
                    print(f"  {name:14} OK ({len(recs)})" if recs else f"  {name:14} EMPTY")
                except Exception as e:
                    failures += 1
                    print(f"  {name:14} FAIL {str(e)[:80]}")
        finally:
            opencli.set_endpoint(None)

    import subprocess

    left = subprocess.run(["pgrep", "-f", str(pdir)], capture_output=True, text=True).stdout.split()
    print(f"\nleftover browser processes: {len(left)} (must be 0)")
    assert not left, "browser was not torn down"
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
