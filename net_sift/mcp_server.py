"""Net-Sift MCP server.

Exposes the engine as MCP tools. Every tool is context-lean: searches write the
full corpus to disk and return only a summary plus the path, so the raw records
never flood the agent. Results, errors, and questions are all that surface.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from . import config, sessions
from . import darkweb as darkweb_mod
from . import doctor as doctor_mod
from . import instagram_recon as ig_mod
from . import search as search_mod
from . import status as status_mod

mcp = MCPServer("net-sift")


@mcp.tool()
def deep_search(
    query: str,
    platforms: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    max_budget: int = config.DEFAULT_BUDGET,
    rank: bool = True,
) -> dict:
    """Sweep many sources for everything said about `query`, rank it, and report
    coverage plus honest gaps.

    platforms: subset of source names (omit for the default keyless set plus any
    connected walled platforms). since/until: YYYY-MM-DD (the window bounds
    retrieval; recency is a ranking boost, not a hard cut). Returns a summary and
    the on-disk corpus path; call resume()/cleanup() to continue or delete it.
    """
    return search_mod.deep_search(
        query, platforms=platforms, since=since, until=until, max_budget=max_budget, rank=rank
    )


@mcp.tool()
def resume(session_id: str, max_budget: int = config.DEFAULT_BUDGET) -> dict:
    """Continue an earlier search: re-run its stored query and parameters to pick up
    anything new, saved as a fresh session."""
    meta = sessions.load_meta(session_id)
    if not meta:
        return {"error": f"no session {session_id}"}
    p = meta.get("params", {})
    return search_mod.deep_search(
        meta["query"],
        platforms=p.get("platforms"),
        since=p.get("since"),
        until=p.get("until"),
        max_budget=max_budget,
        rank=p.get("rank", True),
    )


@mcp.tool()
def list_sessions() -> list:
    """List saved searches (id, query, time, record count, source breakdown)."""
    return sessions.list_sessions()


@mcp.tool()
def cleanup(session_id: str) -> dict:
    """Delete one saved search. Only call after the user confirms they are done
    with it, since it cannot be undone."""
    ok = sessions.cleanup(session_id)
    return {"deleted": ok, "session_id": session_id}


@mcp.tool()
def doctor(probe: bool = False) -> dict:
    """Report which sources net-sift can reach now, and how to connect walled
    platforms. probe=True also live-checks the keyless sources."""
    return doctor_mod.report(probe=probe)


@mcp.tool()
def status() -> dict:
    """Compact connectivity snapshot for a status bar."""
    return status_mod.snapshot()


@mcp.tool()
def darkweb_search(query: str, fetch: int = 0) -> dict:
    """Read-only, information-only discussion search across Tor onion forums.

    Discovers onion forums via onion search indexes and returns public discussion
    text. A non-optional filter drops anything signalling markets, credentials,
    drugs, weapons, or abuse. Needs `tor` installed; it starts and stops its own
    ephemeral Tor. fetch=N also reads the top N forum pages (slower). Returns a
    summary and the on-disk corpus path.
    """
    try:
        records, logs = darkweb_mod.darkweb(query, fetch=fetch)
    except RuntimeError as e:
        return {"error": str(e)}
    meta = sessions.save(query, {"source": "darkweb", "fetch": fetch}, records, logs)
    return {
        "session_id": meta["id"],
        "query": query,
        "total_records": meta["count"],
        "log": logs,
        "top": [{"url": r.get("url"), "text": (r.get("text") or "")[:200]} for r in records[:10]],
        "corpus_path": meta["corpus"],
        "note": "information-only; markets/credentials/illegal categories are filtered out",
        "reminder": f"Corpus kept at {meta['corpus']}. Delete with cleanup('{meta['id']}').",
    }


@mcp.tool()
def instagram_recon(
    op: str,
    handle: str,
    other: str | None = None,
    posts: int = 36,
    per_post: int = 20,
    limit: int = 200,
    max_requests: int = 100,
) -> dict:
    """Per-account Instagram analysis via HikerAPI (opt-in, billed per request).

    op: profile | timeline | where | fans | followers | intersect. `handle` is the
    account (@name); `other` is the second account for intersect. Needs a HikerAPI
    key (set during `net-sift install`, or env HIKERAPI_KEY). Every op is capped at
    `max_requests` billed requests. Returns the analysis and the billed count.
    """
    return ig_mod.run(
        op,
        handle,
        other=other,
        posts=posts,
        per_post=per_post,
        limit=limit,
        max_requests=max_requests,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
