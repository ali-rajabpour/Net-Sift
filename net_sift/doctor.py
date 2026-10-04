"""Health check: what can net-sift reach right now, and what to do if nothing.

Keyless sources are listed (optionally probed live). Walled and web sources run
through a net-sift-managed headless browser launched from a copied profile, so this
reports the chosen browser and which sites that profile is signed into.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone

from . import config
from . import darkweb as darkweb_mod
from . import instagram_recon as ig_mod
from .access import browsers, opencli, profile
from .engine import sources


def _managed() -> dict:
    """Chosen browser id, whether its managed profile exists, and its path."""
    bid = config.get_browser_choice(config.HOME)
    found = browsers.detect()
    managed = profile.managed_dir(config.HOME, bid) if bid else None
    return {
        "browser": bid,
        "browser_present": bool(bid and bid in found),
        "profile": str(managed) if managed else None,
        "profile_ready": bool(managed and managed.is_dir()),
    }


def report(probe: bool = False) -> dict:
    """Structured health report. probe=True live-checks keyless sources (slower)."""
    m = _managed()
    sites = profile.logged_in(m["profile"]) if m["profile_ready"] else {}
    data = {
        "browser": m["browser"] or "none chosen",
        "browser_present": m["browser_present"],
        "managed_profile": m["profile"],
        "profile_ready": m["profile_ready"],
        "node": _node_version(),
        "opencli": "installed"
        if opencli.binary()
        else "not installed (npm i -g @jackwener/opencli)",
        "accounts_logged_in": sorted(s for s, on in sites.items() if on),
        "walled_supported": list(opencli.WALLED_SITES),
        "keyless_sources": list(sources.SOURCES.keys()),
        "web_sources": sorted(opencli.OPEN_SEARCH),
        "optional_env": {
            k: ("set" if config.get_secret(k) else "unset") + f" ({desc})"
            for k, desc in config.OPTIONAL_ENV.items()
        },
        "darkweb": "tor found (available)"
        if darkweb_mod.tor_available()
        else "tor not installed (optional; `brew install tor`)",
        "instagram_recon": "key set (available)"
        if ig_mod.key_present()
        else "no key (optional; run `net-sift install` to add a HikerAPI key)",
    }
    if probe:
        data["keyless_reachable"] = _probe_keyless()
    data["guidance"] = _guidance(m, sites)
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


def _guidance(managed: dict, sites: dict) -> str:
    if not opencli.binary():
        return (
            "Walled and web search are off. Install OpenCLI (npm i -g @jackwener/opencli), "
            "then run `net-sift install`."
        )
    if not managed["profile_ready"]:
        return (
            "No managed browser profile yet. Run `net-sift install` to copy a logged-in "
            "Chromium profile; searches then run headless with the browser closed."
        )
    if not any(sites.values()):
        return (
            "Profile ready, but no accounts detected as signed in. Run "
            "`net-sift login <site>` to add one, or re-run `net-sift install`."
        )
    return (
        "Ready. Walled and web sources run headless from the copied profile. "
        "Add accounts any time with `net-sift login <site>`."
    )


def render(probe: bool = False) -> str:
    d = report(probe=probe)
    lines = ["net-sift doctor", "=" * 40]
    lines.append(f"browser  : {d['browser']}" + ("" if d["browser_present"] else " (not found)"))
    lines.append(
        f"profile  : {d['managed_profile'] or 'none'}"
        + (" [ready]" if d["profile_ready"] else " [not copied]")
    )
    lines.append(f"opencli  : {d['opencli']}")
    lines.append(f"node     : {d['node']}")
    lines.append(f"accounts : {', '.join(d['accounts_logged_in']) or 'none signed in'}")
    lines.append(f"keyless  : {', '.join(d['keyless_sources'])}")
    lines.append(f"web      : {', '.join(d['web_sources'])}")
    lines.append(f"darkweb  : {d['darkweb']}")
    lines.append(f"ig recon : {d['instagram_recon']}")
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
