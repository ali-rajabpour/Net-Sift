"""Engine core: HTTP transport, record shape, dedup, the gap-closing driver, and
the run orchestrator.

The engine is stdlib-only on purpose, so it installs anywhere as plain Python.
A source is a callable ``(query, since, until, budget) -> (records, hit_ceiling)``.
``hit_ceiling`` True means the source refused to page further and the window must
be bisected to recover the tail. ``collect`` does that bisection; ``run`` fans the
sources out, dedups, and ranks.
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from . import ranking

# A browser User-Agent. Several public endpoints reject non-browser agents with a
# 403, which reads as "blocked" when it is really UA filtering.
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
TIMEOUT = 30
RETRIES = 5
PACE = 0.7  # default seconds between two requests to the same host
HOST_PACE = {"api.pullpush.io": 6.0}  # this one throttles far harder than the rest
FATAL = (400, 401, 404, 422)  # not worth retrying; everything else backs off

_last_call: dict[str, float] = {}
_pace_lock = threading.Lock()

Record = dict[str, object]
Source = Callable[[str, datetime | None, datetime | None, int], tuple[list[Record], bool]]


def _get(url: str, headers: dict | None = None) -> bytes:
    """Paced, retrying GET. Honors a per-host pace and backs off on transient errors."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    host = urllib.parse.urlsplit(url).hostname or ""
    pace = HOST_PACE.get(host, PACE)
    last: Exception | None = None
    for attempt in range(RETRIES):
        with _pace_lock:
            gap = pace - (time.time() - _last_call.get(host, 0.0))
            if gap > 0:
                time.sleep(gap)
            _last_call[host] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            last = e
            if getattr(e, "code", None) in FATAL:
                raise
            time.sleep(2**attempt)
    assert last is not None
    raise last


def _json(url: str, headers: dict | None = None):
    return json.loads(_get(url, headers))


def _get_quick(url: str, headers: dict | None = None, timeout: int = 12) -> bytes:
    """Single-shot fetch, no retries. For best-effort enrichment where a slow or
    rate-limited host must fail fast instead of stalling the whole sweep."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _json_quick(url: str, headers: dict | None = None):
    return json.loads(_get_quick(url, headers))


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_day(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def parse_iso(s: str | None) -> datetime | None:
    """Tolerant ISO-8601 parse. Feeds carry 'Z', offsets, and sub-second junk."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def rec(source: str, ident, url, author, text, created, extra: dict | None = None) -> Record:
    """Normalized record. Every source emits this shape so dedup and ranking are uniform."""
    return {
        "source": source,
        "id": f"{source}:{ident}",
        "url": url,
        "author": author,
        "text": (text or "").strip(),
        "created_at": created,
        **(extra or {}),
    }


# --- dedup ----------------------------------------------------------------


def _words(text: str) -> set:
    """Split on non-word characters, not whitespace, so trailing punctuation does
    not fork a token (``scratch.`` vs ``scratch``)."""
    return {w for w in re.split(r"\W+", text.lower()) if w}


def _jaccard(a_words: set, b_words: set) -> float:
    if not a_words or not b_words:
        return 0.0
    return len(a_words & b_words) / len(a_words | b_words)


NEAR_DUP_WINDOW = 300  # compare each record only against the recent window per source


def dedup(records: list[Record], near_dup: float = 0.85, log: list | None = None) -> list[Record]:
    """Exact-id, then exact-text, then near-duplicate collapse within a single source.

    Collapse is deliberately per-source: the same story on two platforms is a
    coverage finding, not noise. Its value is an honest saturation signal, not a
    smaller corpus.
    """
    seen_id, seen_txt, out = set(), set(), []
    recent: dict[str, list] = {}
    collapsed: dict[str, int] = {}
    for r in records:
        if r["id"] in seen_id:
            continue
        seen_id.add(r["id"])

        text = r["text"]
        key = (r["source"], hashlib.sha1(" ".join(sorted(_words(text))).encode()).hexdigest())
        if text and key in seen_txt:
            continue
        seen_txt.add(key)

        words = _words(text)
        if near_dup and len(words) >= 5:
            window = recent.setdefault(r["source"], [])
            if any(_jaccard(words, w) > near_dup for w in window):
                collapsed[r["source"]] = collapsed.get(r["source"], 0) + 1
                continue
            window.append(words)
            if len(window) > NEAR_DUP_WINDOW:
                del window[0]

        out.append(r)

    if log is not None and collapsed:
        for src, n in sorted(collapsed.items(), key=lambda kv: -kv[1]):
            log.append(f"{src}: {n} near-duplicates collapsed (jaccard>{near_dup})")
    return out


# --- gap-closing driver ---------------------------------------------------


def collect(
    fn: Source, name: str, query, since, until, budget, depth: int = 0, log: list | None = None
) -> tuple[list[Record], list]:
    """Run a source; if it reports a ceiling, bisect the window and recurse.

    A ceiling means there is more data than the source will hand over, and a
    narrower window is the only way to reach the tail.
    """
    log = log if log is not None else []
    try:
        recs, ceiling = fn(query, since, until, budget)
    except Exception as e:  # a failed source is a logged gap, never a crashed sweep
        log.append(f"{name}[{depth}] FAILED: {type(e).__name__}: {e}")
        return [], log
    log.append(f"{name}[{depth}] {len(recs)} records{' CEILING' if ceiling else ''}")
    if ceiling and since and until and (until - since) > timedelta(days=1) and depth < 6:
        mid = since + (until - since) / 2
        a, _ = collect(fn, name, query, since, mid, budget, depth + 1, log)
        b, _ = collect(fn, name, query, mid, until, budget, depth + 1, log)
        recs = recs + a + b
    elif ceiling:
        log.append(f"{name}[{depth}] UNRESOLVED GAP: ceiling hit at minimum window")
    return recs, log


def run(
    query: str,
    source_map: dict[str, Source],
    names: list[str],
    since: datetime | None,
    until: datetime | None,
    budget: int,
    near_dup: float = 0.85,
    do_rank: bool = True,
    min_rel: float = ranking.RELEVANCE_FLOOR,
) -> tuple[list[Record], list]:
    """Fan sources out concurrently, dedup, then rank. Returns (records, logs)."""
    logs: list = []
    records: list[Record] = []
    with cf.ThreadPoolExecutor(max_workers=max(1, len(names))) as ex:
        futs = {
            ex.submit(collect, source_map[s], s, query, since, until, budget): s
            for s in names
            if s in source_map
        }
        for f in cf.as_completed(futs):
            recs, log = f.result()
            records += recs
            logs += log
    before = len(records)
    records = dedup(records, near_dup=near_dup, log=logs)
    if do_rank:
        records, dropped = ranking.rank(records, query, floor=min_rel)
        logs.append(f"RANKED kept={len(records)} off_topic_dropped={dropped} floor={min_rel}")
    else:
        records.sort(key=lambda r: r.get("created_at") or "")
    logs.append(f"TOTAL raw={before} deduped={len(records)}")
    return records, logs
