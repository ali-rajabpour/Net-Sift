"""Search facade: merge keyless engine sources with available walled OpenCLI
adapters, run the sweep, persist the session, and return a context-lean summary.

This is the single entry point the MCP server and CLI both call. Callers never get
the raw corpus back, only a summary plus the on-disk path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config, sessions
from .access import opencli
from .engine import core, sources


def all_sources() -> dict[str, core.Source]:
    """Keyless engine sources plus whatever walled OpenCLI adapters are live."""
    merged: dict[str, core.Source] = dict(sources.SOURCES)
    merged.update(opencli.walled_sources())
    return merged


def default_names(source_map: dict[str, core.Source]) -> list[str]:
    walled = [s for s in opencli.WALLED_SITES if s in source_map]
    return list(sources.DEFAULT_SOURCES) + walled


def _coverage(logs: list[str]) -> dict:
    """Derive per-source outcome and the gap list from the engine logs."""
    reached, gaps = {}, []
    for line in logs:
        if "FAILED:" in line:
            gaps.append(line)
        elif "UNRESOLVED GAP" in line:
            gaps.append(line)
        elif line and line[0] not in ("R", "T"):  # skip RANKED / TOTAL summary lines
            name = line.split("[", 1)[0]
            try:
                n = int(line.split("]", 1)[1].strip().split()[0])
                reached[name] = reached.get(name, 0) + n
            except (ValueError, IndexError):
                pass
    return {"reached": reached, "gaps": gaps}


def deep_search(
    query: str,
    platforms: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    max_budget: int = config.DEFAULT_BUDGET,
    rank: bool = True,
    min_rel: float = config.DEFAULT_MIN_REL,
    near_dup: float = config.DEFAULT_NEAR_DUP,
    tg_channels: list[str] | None = None,
    top_n: int = 10,
) -> dict:
    """Run a sweep, save the session, and return a summary (no raw corpus)."""
    source_map = all_sources()
    if tg_channels:
        source_map["telegram"] = lambda q, s, u, b: sources.src_telegram(q, s, u, b, tg_channels)
    names = [p for p in (platforms or default_names(source_map)) if p in source_map]
    unknown = [p for p in (platforms or []) if p not in source_map]

    since_dt = core.parse_day(since) if since else datetime.now(timezone.utc) - timedelta(days=365)
    until_dt = core.parse_day(until) if until else datetime.now(timezone.utc)

    records, logs = core.run(
        query,
        source_map,
        names,
        since_dt,
        until_dt,
        max_budget,
        near_dup=near_dup,
        do_rank=rank,
        min_rel=min_rel,
    )
    params = {
        "platforms": names,
        "since": since,
        "until": until,
        "max_budget": max_budget,
        "rank": rank,
        "min_rel": min_rel,
        "near_dup": near_dup,
    }
    meta = sessions.save(query, params, records, logs)
    cov = _coverage(logs)

    return {
        "session_id": meta["id"],
        "query": query,
        "total_records": meta["count"],
        "by_source": meta["sources"],
        "coverage": cov["reached"],
        "gaps": cov["gaps"],
        "unknown_platforms": unknown,
        "top": [
            {
                "source": r.get("source"),
                "score": r.get("_score"),
                "url": r.get("url"),
                "text": (r.get("text") or "")[:200],
            }
            for r in records[:top_n]
        ],
        "corpus_path": meta["corpus"],
        "reminder": (
            f"Corpus kept at {meta['corpus']} ({meta['count']} records). "
            f"Continue it later with resume('{meta['id']}'), or delete it with "
            f"cleanup('{meta['id']}') once you confirm you are done."
        ),
    }
