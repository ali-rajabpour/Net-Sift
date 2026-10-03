"""Health check: what can net-sift reach right now, and what to do if nothing.

Keyless sources are listed (optionally probed live). Walled platforms report
through OpenCLI without spending or writing. The scaffolding mirrors the pattern
in Agent Reach (MIT).
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timedelta, timezone

from . import config
from .access import opencli
from .engine import sources


def report(probe: bool = False) -> dict:
    """Structured health report. probe=True live-checks keyless sources (slower).

    OpenCLI connectivity is checked once and reused, since each check runs
    `opencli doctor` (a few seconds); calling it several times also made the
    summary contradict itself.
    """
    connected = opencli.available()
    walled = opencli.walled_sources(connected=connected)
    data = {
        "opencli": opencli.status(connected=connected),
        "node": _node_version(),
        "walled_available": sorted(walled.keys()),
        "walled_supported": list(opencli.WALLED_SITES),
        "keyless_sources": list(sources.SOURCES.keys()),
        "optional_env": {
            k: ("set" if os.environ.get(k) else "unset") + f" ({desc})"
            for k, desc in config.OPTIONAL_ENV.items()
        },
    }
    if probe:
        data["keyless_reachable"] = _probe_keyless()
    data["guidance"] = _guidance(connected, walled)
    return data


def _node_version() -> str:
    exe = shutil.which("node")
    if not exe:
        return "not installed (OpenCLI needs Node >= 20.18.1)"
    import subprocess

    try:
        v = subprocess.run(
            [exe, "--version"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return v or "installed"
    except (OSError, subprocess.SubprocessError):
        return "installed"


def _probe_keyless() -> dict:
    now = datetime.now(timezone.utc)
    out = {}
    for name, fn in sources.SOURCES.items():
        if name == "telegram":  # needs channels; skip in a generic probe
            out[name] = "skipped (needs --channels)"
            continue
        try:
            recs, _ = fn("test", now - timedelta(days=30), now, 3)
            out[name] = f"ok ({len(recs)})"
        except Exception as e:
            out[name] = f"unreachable: {type(e).__name__}"
    return out


def _guidance(connected: bool, walled: dict) -> str:
    if connected and walled:
        return (
            "Browser connected. Accounts you are logged into are searchable; run "
            "`net-sift install` to check each account and log into any you want to add."
        )
    if not opencli.binary():
        return (
            "Account search is off. Install OpenCLI (npm i -g @jackwener/opencli or the "
            "OpenCLIApp), then run `net-sift install` to connect your browser and accounts."
        )
    return (
        "Browser not connected. Open a Chromium browser with the OpenCLI extension enabled, "
        "then run `net-sift install` to connect your accounts."
    )


def render(probe: bool = False) -> str:
    d = report(probe=probe)
    lines = ["net-sift doctor", "=" * 40]
    lines.append(f"opencli  : {d['opencli']}")
    lines.append(f"node     : {d['node']}")
    lines.append(f"accounts : {', '.join(d['walled_available']) or 'none connected'}")
    lines.append(f"keyless  : {', '.join(d['keyless_sources'])}")
    lines.append("env     :")
    for k, v in d["optional_env"].items():
        lines.append(f"  {k}: {v}")
    if "keyless_reachable" in d:
        lines.append("keyless reachability:")
        for k, v in d["keyless_reachable"].items():
            lines.append(f"  {k:14} {v}")
    lines.append("")
    lines.append(d["guidance"])
    return "\n".join(lines)
