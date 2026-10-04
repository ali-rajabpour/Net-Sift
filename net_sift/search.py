"""Search facade: merge keyless engine sources with available walled OpenCLI
adapters, run the sweep, persist the session, and return a context-lean summary.

This is the single entry point the MCP server and CLI both call. Callers never get
the raw corpus back, only a summary plus the on-disk path.
"""

from __future__ import annotations

import contextlib
import os
from datetime import datetime, timedelta, timezone

from . import config, sessions
from .access import browser, browsers, opencli, profile
from .engine import core, sources


def _managed_profile() -> tuple[str, str] | None:
    """(executable, managed profile dir) for the chosen browser, if its managed copy
    exists. Choice comes from NET_SIFT_BROWSER or the wizard's saved pick."""
    bid = os.environ.get("NET_SIFT_BROWSER") or config.get_browser_choice(config.HOME)
    if not bid:
        return None
    found = browsers.detect().get(bid)
    if not found:
        return None
    managed = profile.managed_dir(config.HOME, bid)
    if not managed.is_dir():
        return None
    return found["executable"], str(managed)


def _needs_browser(names: list[str], source_map: dict) -> bool:
    browser_sources = set(opencli.WALLED_SITES) | set(opencli.OPEN_SEARCH)
    return any(n in browser_sources for n in names)


def all_sources(with_browser: bool = False) -> dict[str, core.Source]:
    """Keyless engine sources, the Brave Search API when keyed, and, when a managed
    browser will be opened for this sweep, the OpenCLI walled and open-web sources."""
    merged: dict[str, core.Source] = dict(sources.SOURCES)
    if with_browser:
        merged.update(opencli.walled_sources(connected=True))
        merged.update(opencli.open_sources(connected=True))
    # Keyless `brave` comes from the browser (OPEN_SEARCH). The Brave Search API is a
    # separate keyed path, `brave_api`, for when there is no managed profile.
    brave_key = config.get_secret("BRAVE_API_KEY")
    if brave_key:
        merged["brave_api"] = lambda q, s, u, b: sources.src_brave(q, s, u, b, brave_key)
    fc_key = config.get_secret("FIRECRAWL_API_KEY")
    if fc_key:
        merged["firecrawl"] = lambda q, s, u, b: sources.src_firecrawl(q, s, u, b, fc_key)
    return merged


def default_names(source_map: dict[str, core.Source]) -> list[str]:
    names = list(sources.DEFAULT_SOURCES)
    if config.get_secret("MARGINALIA_API_KEY"):
        names.append("marginalia")
    if config.get_secret("CONTEXT7_API_KEY"):
        names.append("context7")
    live = (*opencli.WALLED_SITES, *opencli.OPEN_SEARCH, "brave_api", "firecrawl")
    return names + [s for s in live if s in source_map]


def discover_telegram(query: str, source_map: dict[str, core.Source]) -> list[str]:
    """Telegram has no cross-channel search. Ask Google which public channels cover
    the topic, so the telegram source has a channel list to read."""
    recs, _ = source_map["google"](sources.TELEGRAM_DISCOVERY.format(query=query), None, None, 10)
    return sources.telegram_channels(str(r.get("url") or "") for r in recs)


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
    managed = _managed_profile()
    source_map = all_sources(with_browser=managed is not None)
    names = [p for p in (platforms or default_names(source_map)) if p in source_map]
    unknown = [p for p in (platforms or []) if p not in source_map]
    extra_gaps: list[str] = []
    if managed is None and platforms and _needs_browser(platforms, source_map):
        extra_gaps.append("browser[0] FAILED: no managed profile; run `net-sift install`")

    since_dt = core.parse_day(since) if since else datetime.now(timezone.utc) - timedelta(days=365)
    until_dt = core.parse_day(until) if until else datetime.now(timezone.utc)

    # Browser-backed sources (walled + open web + telegram discovery) run inside one
    # managed headless browser, opened once and killed at the end.
    open_browser = managed is not None and _needs_browser(names, source_map)
    cm = (
        browser.managed_browser(managed[0], managed[1])
        if open_browser
        else contextlib.nullcontext(None)
    )
    with cm as endpoint:
        if endpoint:
            opencli.set_endpoint(endpoint)
        try:
            wants_telegram = platforms is None or "telegram" in platforms
            if not tg_channels and wants_telegram and "google" in source_map:
                try:
                    tg_channels = discover_telegram(query, source_map)
                except Exception as e:  # a failed discovery is a declared gap
                    extra_gaps.append(
                        f"telegram[0] FAILED: channel discovery: {type(e).__name__}: {e}"
                    )
            if tg_channels:
                source_map["telegram"] = lambda q, s, u, b: sources.src_telegram(
                    q, s, u, b, tg_channels
                )
                if "telegram" not in names:
                    names.append("telegram")
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
        finally:
            opencli.set_endpoint(None)
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
    cov["gaps"].extend(extra_gaps)

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
