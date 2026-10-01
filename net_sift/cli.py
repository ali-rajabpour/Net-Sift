"""net-sift command line: serve the MCP, run the doctor, print status, and install
into Claude Code and Codex.

The install writers are small, idempotent, and take explicit paths so they can be
tested against a temp home without touching a real config.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from . import __version__
from . import doctor as doctor_mod
from . import search as search_mod
from . import status as status_mod

MCP_ENTRY = {"command": "net-sift", "args": ["serve"]}


# --- install writers (pure, testable) -------------------------------------


def merge_json_mcp(path: Path) -> str:
    """Add the net-sift MCP server to a Claude-style ~/.claude.json."""
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return f"skipped {path} (not valid JSON; add net-sift manually)"
    servers = data.setdefault("mcpServers", {})
    if servers.get("net-sift") == MCP_ENTRY:
        return f"already present in {path}"
    servers["net-sift"] = MCP_ENTRY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"registered MCP in {path}"


def ensure_statusline(path: Path) -> str:
    """Set the Claude Code status bar to net-sift in settings.json."""
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return f"skipped {path} (not valid JSON; add statusLine manually)"
    line = {"type": "command", "command": "net-sift status --line", "padding": 0}
    if data.get("statusLine") == line:
        return f"status bar already set in {path}"
    data["statusLine"] = line
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"status bar set in {path}"


def ensure_codex(path: Path) -> str:
    """Add [mcp_servers.net-sift] to a Codex config.toml without rewriting the file."""
    block = '\n[mcp_servers.net-sift]\ncommand = "net-sift"\nargs = ["serve"]\n'
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if "[mcp_servers.net-sift]" in existing:
        return f"already present in {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(existing + block, encoding="utf-8")
    return f"registered MCP in {path}"


# --- commands -------------------------------------------------------------


def _cmd_install(args) -> int:
    home = Path.home()
    print("Installing net-sift for Claude Code and Codex...\n")
    for msg in (
        merge_json_mcp(home / ".claude.json"),
        ensure_statusline(home / ".claude" / "settings.json"),
        ensure_codex(home / ".codex" / "config.toml"),
    ):
        print("  " + msg)

    print("\nDependency check:")
    print("  node   :", doctor_mod._node_version())
    print(
        "  opencli:",
        "found"
        if shutil.which("opencli")
        else "missing (npm i -g @jackwener/opencli, or install OpenCLIApp)",
    )
    print("\n" + doctor_mod.render())
    print("\nRestart your client so it picks up the MCP server.")
    return 0


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

    sub.add_parser(
        "install", help="register the MCP + status bar in Claude Code and Codex"
    ).set_defaults(func=_cmd_install)
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
