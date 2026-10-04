"""net-sift command line: serve the MCP, run the doctor, print status, search, and
run the install wizard.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import __version__, installer
from . import doctor as doctor_mod
from . import search as search_mod
from . import status as status_mod

# Re-exported so the config writers keep one public home (and stay test-addressable).
MCP_ENTRY = installer.MCP_ENTRY
merge_json_mcp = installer.merge_json_mcp
ensure_statusline = installer.ensure_statusline
ensure_codex = installer.ensure_codex


def _cmd_install(args) -> int:
    return installer.run(Path.home(), assume_yes=args.yes)


def _cmd_login(args) -> int:
    from .access import opencli

    sites = args.sites.split(",") if args.sites else list(opencli.WALLED_SITES)
    sites = [s for s in sites if s in installer.LOGIN_URLS]
    if not sites:
        print("No known sites to log into.")
        return 1
    ui = installer._UI(assume_yes=False)
    res = installer.login_sites(Path.home(), sites, ui)
    return 0 if any(res.values()) else 1


def _cmd_serve(args) -> int:
    from .mcp_server import main as serve

    serve()
    return 0


def _cmd_doctor(args) -> int:
    print(doctor_mod.render(probe=args.probe))
    return 0


def _cmd_status(args) -> int:
    if args.line:
        print(status_mod.line())
    else:
        print(json.dumps(status_mod.snapshot(), indent=2))
    return 0


def _cmd_search(args) -> int:
    platforms = args.platforms.split(",") if args.platforms else None
    res = search_mod.deep_search(
        args.query, platforms=platforms, since=args.since, until=args.until, max_budget=args.max
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return 0


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="net-sift", description="Coverage-first social and web deep-search (MCP)."
    )
    ap.add_argument("--version", action="version", version=f"net-sift {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("install", help="guided setup: MCP, status bar, OpenCLI, browser")
    i.add_argument(
        "--yes", action="store_true", help="unattended: accept installs, skip human-only steps"
    )
    i.set_defaults(func=_cmd_install)

    lg = sub.add_parser("login", help="log into walled platforms in the managed browser")
    lg.add_argument("sites", nargs="?", help="comma-separated site ids (default: all walled)")
    lg.set_defaults(func=_cmd_login)

    sub.add_parser("serve", help="run the MCP server (stdio)").set_defaults(func=_cmd_serve)

    d = sub.add_parser("doctor", help="what can net-sift reach right now")
    d.add_argument("--probe", action="store_true", help="also live-check keyless sources")
    d.set_defaults(func=_cmd_doctor)

    s = sub.add_parser("status", help="connectivity snapshot")
    s.add_argument("--line", action="store_true", help="one-line form for a status bar")
    s.set_defaults(func=_cmd_status)

    q = sub.add_parser("search", help="run a search locally (prints the summary)")
    q.add_argument("query")
    q.add_argument("--platforms", help="comma-separated source names")
    q.add_argument("--since", help="YYYY-MM-DD")
    q.add_argument("--until", help="YYYY-MM-DD")
    q.add_argument("--max", type=int, default=200, help="per-source budget")
    q.set_defaults(func=_cmd_search)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
