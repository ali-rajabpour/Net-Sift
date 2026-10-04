"""Keyless sources: no login required. Each is a callable
``(query, since, until, budget) -> (records, hit_ceiling)``.

Walled login platforms (X, Reddit, Instagram, Facebook, Bilibili, Xiaohongshu)
are not here: they are reached through the logged-in browser in
``net_sift.access.opencli``. Optional API keys are read from the environment only
(never a config file or OS keychain), so the tool stays portable.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from datetime import datetime, timezone

# defusedxml hardens against entity-expansion and external-entity attacks when
# parsing remote feeds. Security at a trust boundary is worth the one dependency.
import defusedxml.ElementTree as ET

from . import ranking
from .core import Record, _get, _json, parse_iso, rec


def _relevant(query: str, text: str) -> bool:
    """Source-side floor for OR-matched feeds, backed by the shared ranker. The
    global ranker runs again later; this keeps a noisy source from flooding."""
    if not query or not text:
        return True
    return ranking.relevance(query, text) >= ranking.RELEVANCE_FLOOR


def src_bluesky(query, since, until, budget):
    """AT Protocol AppView. Keyless, cursor-paged. Uses api.bsky.app (the public
    host 403s some egress) and filters the window client-side (it 403s on
    since/until params)."""
    out: list[Record] = []
    cursor, ceiling = None, False
    base = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
    while len(out) < budget:
        p = {"q": query, "limit": 100, "sort": "latest"}
        if cursor:
            p["cursor"] = cursor
        d = _json(f"{base}?{urllib.parse.urlencode(p)}")
        posts = d.get("posts", [])
        past = False
        for x in posts:
            r = x.get("record", {})
            when = parse_iso(r.get("createdAt"))
            if when:
                if until and when > until:
                    continue
                if since and when < since:
                    past = True
                    continue
            handle = x.get("author", {}).get("handle", "")
            rkey = (x.get("uri") or "").rsplit("/", 1)[-1]
            out.append(
                rec(
                    "bluesky",
                    x.get("uri"),
                    f"https://bsky.app/profile/{handle}/post/{rkey}",
                    handle,
                    r.get("text"),
                    r.get("createdAt"),
                    {"likes": x.get("likeCount"), "reposts": x.get("repostCount")},
                )
            )
        if past:
            break
        cursor = d.get("cursor")
        if not cursor or not posts:
            break
        if len(out) >= 1000 and cursor:
            ceiling = True
            break
    return out, ceiling


def src_hackernews(query, since, until, budget):
    """Algolia HN index. Keyless, offset-paged, hard 1000-hit ceiling per query."""
    out: list[Record] = []
    page, ceiling = 0, False
    nf = []
    if since:
        nf.append(f"created_at_i>{int(since.timestamp())}")
    if until:
        nf.append(f"created_at_i<{int(until.timestamp())}")
    while len(out) < budget:
        p = {"query": query, "hitsPerPage": 100, "page": page}
        if nf:
            p["numericFilters"] = ",".join(nf)
        d = _json("https://hn.algolia.com/api/v1/search_by_date?" + urllib.parse.urlencode(p))
        for x in d.get("hits", []):
            out.append(
                rec(
                    "hackernews",
                    x.get("objectID"),
                    f"https://news.ycombinator.com/item?id={x.get('objectID')}",
                    x.get("author"),
                    x.get("title") or x.get("comment_text") or x.get("story_text"),
                    x.get("created_at"),
                    {"points": x.get("points")},
                )
            )
        page += 1
        if page >= d.get("nbPages", 0):
            break
        if page >= 10:
            ceiling = True
            break
    return out, ceiling


def src_github(query, since, until, budget):
    """GitHub repos + issues/PRs via the keyless Search API. Optional GITHUB_TOKEN
    (env) lifts the rate limit. Each endpoint stops at 1000 results per query, so a
    full run inside a date window is a ceiling the driver can bisect."""
    hdr = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        hdr["Authorization"] = f"Bearer {tok}"
    out: list[Record] = []
    ceiling = False

    window = f"{since:%Y-%m-%d}..{until:%Y-%m-%d}" if since and until else None

    def sweep(path, date_field, to_rec):
        nonlocal ceiling
        q = f"{query} {date_field}:{window}" if window else query
        for page in range(1, 11):
            if len(out) >= budget:
                return
            p = {"q": q, "sort": "updated", "order": "desc", "per_page": 100, "page": page}
            try:
                d = _json(f"https://api.github.com/search/{path}?{urllib.parse.urlencode(p)}", hdr)
            except Exception:
                if not out:
                    raise  # nothing collected: report the failure as a gap
                return  # rate limited part way: keep what arrived
            items = d.get("items") or []
            for x in items:
                r = to_rec(x)
                if r:
                    out.append(r)
            if len(items) < 100:
                return
        ceiling = bool(window)

    sweep(
        "repositories",
        "pushed",
        lambda x: rec(
            "github",
            f"repo:{x.get('id')}",
            x.get("html_url"),
            (x.get("owner") or {}).get("login"),
            f"{x.get('full_name', '')}\n{x.get('description') or ''}",
            x.get("pushed_at") or x.get("updated_at"),
            {"stars": x.get("stargazers_count"), "kind": "repo", "language": x.get("language")},
        ),
    )
    sweep(
        "issues",
        "updated",
        lambda x: rec(
            "github",
            f"issue:{x.get('id')}",
            x.get("html_url"),
            (x.get("user") or {}).get("login"),
            f"{x.get('title', '')}\n{(x.get('body') or '')[:2000]}",
            x.get("updated_at") or x.get("created_at"),
            {"comments": x.get("comments"), "kind": "pr" if x.get("pull_request") else "issue"},
        ),
    )
    return out[:budget], ceiling


def src_arxiv(query, since, until, budget):
    """arXiv Atom API. Keyless, newest-first. Multi-word queries are quoted into a
    phrase, else arXiv applies the field prefix only to the first term and drifts."""
    out: list[Record] = []
    start, ceiling = 0, False
    ns = {"a": "http://www.w3.org/2005/Atom"}
    words = query.split()
    sq = f'all:"{query}"' if len(words) > 1 else f"all:{query}"
    while len(out) < budget:
        p = {
            "search_query": sq,
            "start": start,
            "max_results": 100,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        raw = _get(f"https://export.arxiv.org/api/query?{urllib.parse.urlencode(p)}")
        root = ET.fromstring(raw)
        entries = root.findall("a:entry", ns)
        if not entries:
            break
        past = False
        for e in entries:
            pub = e.findtext("a:published", "", ns)
            when = parse_iso(pub)
            if when:
                if until and when > until:
                    continue
                if since and when < since:
                    past = True
                    continue
            url = (e.findtext("a:id", "", ns) or "").strip()
            title = re.sub(r"\s+", " ", e.findtext("a:title", "", ns) or "").strip()
            summary = re.sub(r"\s+", " ", e.findtext("a:summary", "", ns) or "").strip()
            authors = ", ".join(a.findtext("a:name", "", ns) for a in e.findall("a:author", ns))
            out.append(
                rec(
                    "arxiv",
                    url,
                    url,
                    authors,
                    f"{title}\n{summary}",
                    pub,
                    {"primary_category": _arxiv_cat(e)},
                )
            )
        if past:
            break
        start += len(entries)
        if len(entries) < 100:
            break
    return out[:budget], ceiling


def _arxiv_cat(entry):
    el = entry.find("{http://arxiv.org/schemas/atom}primary_category")
    return el.get("term") if el is not None else None


def src_polymarket(query, since, until, budget):
    """Polymarket prediction markets via the keyless Gamma API."""
    p = {"limit": min(budget, 100), "active": "true", "closed": "false", "search": query}
    events = _json(f"https://gamma-api.polymarket.com/events?{urllib.parse.urlencode(p)}")
    if not isinstance(events, list):
        events = events.get("data", []) if isinstance(events, dict) else []
    out: list[Record] = []
    for e in events[:budget]:
        vol = e.get("volume") or e.get("volume24hr")
        out.append(
            rec(
                "polymarket",
                e.get("id"),
                f"https://polymarket.com/event/{e.get('slug', '')}",
                "polymarket",
                f"{e.get('title', '')}\n{(e.get('description') or '')[:1500]}",
                e.get("startDate") or e.get("createdAt"),
                {"volume": int(float(vol)) if vol else None, "liquidity": e.get("liquidity")},
            )
        )
    return out, False


def src_stocktwits(query, since, until, budget):
    """StockTwits cashtag stream (keyless). The query is read as a ticker; a
    non-ticker query returns empty."""
    sym = re.sub(r"[^A-Za-z.]", "", query.split()[0] if query.split() else query).upper()
    if not sym:
        return [], False
    try:
        d = _json(f"https://api.stocktwits.com/api/2/streams/symbol/{sym}.json")
    except Exception:
        return [], False
    out: list[Record] = []
    for m in (d.get("messages") or [])[:budget]:
        u = m.get("user") or {}
        out.append(
            rec(
                "stocktwits",
                m.get("id"),
                f"https://stocktwits.com/{u.get('username', '')}/message/{m.get('id')}",
                u.get("username"),
                m.get("body"),
                m.get("created_at"),
                {"symbol": sym, "likes": (m.get("likes") or {}).get("total")},
            )
        )
    return out, False


def src_mastodon(query, since, until, budget, instances=("mastodon.social", "fosstodon.org")):
    """Public hashtag timelines. Keyless; free-text search needs auth, tags do not."""
    out: list[Record] = []
    tag = urllib.parse.quote(query.replace("#", "").replace(" ", ""))
    for host in instances:
        max_id = None
        while len(out) < budget:
            p = {"limit": 40}
            if max_id:
                p["max_id"] = max_id
            try:
                items = _json(
                    f"https://{host}/api/v1/timelines/tag/{tag}?" + urllib.parse.urlencode(p)
                )
            except Exception:
                break
            if not items:
                break
            for x in items:
                out.append(
                    rec(
                        "mastodon",
                        x.get("uri"),
                        x.get("url"),
                        (x.get("account") or {}).get("acct"),
                        re.sub(r"<[^>]+>", " ", x.get("content") or ""),
                        x.get("created_at"),
                        {"instance": host},
                    )
                )
            max_id = items[-1].get("id")
            if len(items) < 40:
                break
    return out, False


def src_habr(query, since, until, budget):
    """Habr, the major Russian-language IT community. Keyless search RSS."""
    raw = _get(
        "https://habr.com/en/rss/search/?"
        + urllib.parse.urlencode({"q": query, "target_type": "posts", "order": "relevance"})
    )
    out: list[Record] = []
    root = ET.fromstring(raw)
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", item.findtext("description") or "")
        desc = re.sub(r"\s+", " ", desc).strip()
        body = f"{title}\n{desc}"
        if _relevant(query, body):
            out.append(rec("habr", link or title, link, "", body, item.findtext("pubDate")))
    return out, False


def src_v2ex(query, since, until, budget):
    """V2EX, a large Chinese developer community. Full-text via sov2ex."""
    out: list[Record] = []
    frm = 0
    while len(out) < budget:
        p = {"q": query, "size": 50, "from": frm, "sort": "created", "order": "0"}
        d = _json("https://www.sov2ex.com/api/search?" + urllib.parse.urlencode(p))
        hits = d.get("hits", [])
        if not hits:
            break
        for h in hits:
            s = h.get("_source", {})
            tid = s.get("id") or h.get("_id")
            created = s.get("created")
            iso_s = None
            if isinstance(created, (int, float)) and created > 1_000_000_000:
                iso_s = datetime.fromtimestamp(created, timezone.utc).isoformat()
            body = f"{s.get('title', '')}\n{s.get('content', '')}"
            if _relevant(query, body):
                out.append(
                    rec(
                        "v2ex",
                        tid,
                        f"https://www.v2ex.com/t/{tid}",
                        s.get("member") or "",
                        body,
                        iso_s,
                        {"replies": s.get("replies"), "node": s.get("node")},
                    )
                )
        frm += len(hits)
        total = d.get("total")
        total = total.get("value") if isinstance(total, dict) else total
        if total is not None and frm >= total:
            break
    return out, False


def src_telegram(query, since, until, budget, channels=None):
    """Public Telegram channels via the keyless t.me/s/ web preview. Telegram has
    no cross-channel search, so this needs a channel list and sees recent history.

    The preview page ignores the date window, so this never reports a ceiling:
    bisecting would only fetch the same pages again."""
    channels = channels or []
    if not channels:
        raise RuntimeError("no channel list (pass channels, or connect a browser for discovery)")
    out: list[Record] = []
    for ch in channels:
        if len(out) >= budget:
            break
        try:
            html = _get(f"https://t.me/s/{urllib.parse.quote(ch)}").decode("utf-8", "replace")
        except Exception:
            continue
        for m in re.finditer(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.S
        ):
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()
            if not _relevant(query, text):
                continue
            head = html[: m.start()]
            link = (re.findall(r'href="(https://t\.me/[^"]+/\d+)"', head) or [""])[-1]
            when = (re.findall(r'datetime="([^"]+)"', head) or [None])[-1]
            at = parse_iso(when)
            if at and ((since and at < since) or (until and at > until)):
                continue
            out.append(rec("telegram", link or f"{ch}:{len(out)}", link, ch, text, when))
    return out, False


def src_sogou_wechat(query, since, until, budget):
    """Sogou WeChat search: public-account articles, otherwise walled off. Chinese
    content, single page (Sogou captchas aggressively), snippet-level.

    The search ignores the date window, so this never reports a ceiling: bisecting
    would repeat the same request and trip the captcha sooner."""
    html = _get(
        "https://weixin.sogou.com/weixin?" + urllib.parse.urlencode({"type": "2", "query": query})
    ).decode("utf-8", "replace")
    if re.search(r"antispider|验证码", html):
        raise RuntimeError("blocked by the Sogou captcha")
    out: list[Record] = []
    for b in re.findall(r'<li[^>]*id="sogou_vr[^"]*"[\s\S]*?</li>', html):
        title = re.sub(
            r"<[^>]+>", "", (re.search(r"<h3[^>]*>(.*?)</h3>", b, re.S) or [None, ""])[1]
        ).strip()
        snip = re.sub(
            r"<[^>]+>",
            "",
            (re.search(r'class="txt-info"[^>]*>(.*?)</p>', b, re.S) or [None, ""])[1],
        ).strip()
        acct = re.sub(
            r"<[^>]+>", "", (re.search(r'class="account"[^>]*>(.*?)</a>', b, re.S) or [None, ""])[1]
        ).strip()
        link = (re.search(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"', b) or [None, ""])[1]
        body = f"{title}\n{snip}"
        if title and _relevant(query, body):
            out.append(
                rec(
                    "sogou_wechat",
                    link or title,
                    ("https://weixin.sogou.com" + link) if link.startswith("/") else link,
                    acct,
                    body,
                    None,
                )
            )
    return out, False


def src_gdelt(query, since, until, budget):
    """GDELT DOC 2.0: worldwide news in 65 languages, keyless. One call returns at
    most 250 articles, so a full page is a ceiling and the driver bisects the window."""
    p = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": 250,
        "sort": "datedesc",
    }
    if since:
        p["startdatetime"] = since.strftime("%Y%m%d%H%M%S")
    if until:
        p["enddatetime"] = until.strftime("%Y%m%d%H%M%S")
    raw = _get("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(p))
    body = raw.decode("utf-8", "replace").strip()
    if not body.startswith("{"):
        # Throttling and rejected queries come back as plain text with a 200.
        raise RuntimeError(body[:120] or "empty response")
    arts = json.loads(body, strict=False).get("articles", [])
    out: list[Record] = []
    for a in arts[:budget]:
        try:
            when = (
                datetime.strptime(a.get("seendate", ""), "%Y%m%dT%H%M%SZ")
                .replace(tzinfo=timezone.utc)
                .isoformat()
            )
        except ValueError:
            when = None
        out.append(
            rec(
                "gdelt",
                a.get("url"),
                a.get("url"),
                a.get("domain"),
                a.get("title"),
                when,
                {"language": a.get("language"), "country": a.get("sourcecountry")},
            )
        )
    return out, len(arts) >= 250


def src_marginalia(query, since, until, budget):
    """Marginalia: an independent index of the small, non-commercial web. Results
    are undated. The shared `public` key runs out most days, so the source joins the
    default set only when MARGINALIA_API_KEY holds a personal key."""
    d = _json(
        "https://api2.marginalia-search.com/search?"
        + urllib.parse.urlencode({"query": query, "count": min(budget, 100)}),
        {"API-Key": os.environ.get("MARGINALIA_API_KEY", "public")},
    )
    out = [
        rec(
            "marginalia",
            x.get("url"),
            x.get("url"),
            None,
            f"{x.get('title') or ''}\n{x.get('description') or ''}",
            None,
        )
        for x in d.get("results", [])[:budget]
    ]
    return out, False


def src_context7(query, since, until, budget, key=None):
    """Context7: up-to-date code and library documentation for a natural-language
    query. Keyed (CONTEXT7_API_KEY); undated, so it never reports a ceiling."""
    key = key or os.environ.get("CONTEXT7_API_KEY")
    if not key:
        raise RuntimeError("CONTEXT7_API_KEY is not set")
    d = _json(
        "https://context7.com/api/v3/search?" + urllib.parse.urlencode({"query": query}),
        {"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    out: list[Record] = []
    for s in d.get("codeSnippets", []):
        if len(out) >= budget:
            break
        code = "\n".join(c.get("code", "") for c in s.get("codeList", []))
        lib = s.get("libraryId", "")
        out.append(
            rec(
                "context7",
                f"{lib}:{s.get('codeTitle', '')}",
                f"https://context7.com{lib}" if lib.startswith("/") else lib,
                lib,
                f"{s.get('codeTitle', '')}\n{code}",
                None,
            )
        )
    for s in d.get("infoSnippets", []):
        if len(out) >= budget:
            break
        lib = s.get("libraryId", "")
        out.append(
            rec(
                "context7",
                f"{lib}:{abs(hash(s.get('content', ''))) % 10**10}",
                f"https://context7.com{lib}" if lib.startswith("/") else lib,
                lib,
                s.get("content", ""),
                None,
            )
        )
    return out[:budget], False


def src_firecrawl(query, since, until, budget, key=None):
    """Firecrawl search API: a hosted crawler with stealth proxies that reaches
    sites our own browser gets blocked on (Google, Cloudflare-walled pages). Keyed
    (FIRECRAWL_API_KEY); metered; queries and URLs go to Firecrawl's servers."""
    key = key or os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY is not set")
    payload = {"query": query, "limit": min(budget, 100), "sources": ["web"]}
    if since and until:
        payload["tbs"] = f"cdr:1,cd_min:{since:%m/%d/%Y},cd_max:{until:%m/%d/%Y}"
    d = _json(
        "https://api.firecrawl.dev/v2/search",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json.dumps(payload).encode(),
    )
    web = (d.get("data") or {}).get("web") or []
    out = [
        rec(
            "firecrawl",
            x.get("url"),
            x.get("url"),
            None,
            f"{x.get('title') or ''}\n{x.get('description') or ''}",
            None,
        )
        for x in web[:budget]
    ]
    return out, False


BRAVE_PAGE = 20  # the API's maximum per request
BRAVE_MAX_PAGES = 10  # offset stops at 9, so 200 results is the whole reach


def src_brave(query, since, until, budget, key=None):
    """Brave Search API: an independent general web index. Metered, so it needs
    BRAVE_API_KEY and is never bisected: one sweep costs at most 10 requests and the
    tail past 200 results is a declared gap, not a reason to spend more."""
    key = key or os.environ.get("BRAVE_API_KEY")
    if not key:
        raise RuntimeError("BRAVE_API_KEY is not set")
    p = {"q": query, "count": BRAVE_PAGE}
    if since and until:
        p["freshness"] = f"{since:%Y-%m-%d}to{until:%Y-%m-%d}"
    out: list[Record] = []
    for page in range(BRAVE_MAX_PAGES):
        if len(out) >= budget:
            break
        d = _json(
            "https://api.search.brave.com/res/v1/web/search?"
            + urllib.parse.urlencode({**p, "offset": page}),
            {"X-Subscription-Token": key, "Accept": "application/json"},
        )
        results = (d.get("web") or {}).get("results", [])
        for x in results:
            out.append(
                rec(
                    "brave",
                    x.get("url"),
                    x.get("url"),
                    (x.get("profile") or {}).get("name"),
                    f"{x.get('title') or ''}\n{x.get('description') or ''}",
                    x.get("page_age"),
                )
            )
        if len(results) < BRAVE_PAGE or not (d.get("query") or {}).get("more_results_available"):
            break
    return out[:budget], False


# t.me paths that are not channel names.
_TG_RESERVED = {
    "joinchat",
    "addstickers",
    "addemoji",
    "addlist",
    "share",
    "proxy",
    "socks",
    "login",
}

#: Search-engine query that surfaces public channel pages for a topic. The word
#: "subscribers" is on every channel preview page and on no other t.me page.
TELEGRAM_DISCOVERY = "site:t.me subscribers {query}"


def telegram_channels(urls) -> list[str]:
    """Channel names from t.me result URLs, in first-seen order."""
    seen: dict[str, None] = {}
    for u in urls:
        m = re.match(r"https?://t\.me/(?:s/)?([A-Za-z0-9_]{4,})", u or "")
        if m and m.group(1).lower() not in _TG_RESERVED:
            seen.setdefault(m.group(1), None)
    return list(seen)


# Registry. Default set is broad keyless coverage. telegram needs a channel list
# (given, or discovered through a web search source), marginalia a personal key,
# and brave is keyed and registered by the search facade, so none is a default here.
SOURCES = {
    "bluesky": src_bluesky,
    "hackernews": src_hackernews,
    "github": src_github,
    "arxiv": src_arxiv,
    "polymarket": src_polymarket,
    "stocktwits": src_stocktwits,
    "mastodon": src_mastodon,
    "habr": src_habr,
    "v2ex": src_v2ex,
    "telegram": src_telegram,
    "sogou_wechat": src_sogou_wechat,
    "gdelt": src_gdelt,
    "marginalia": src_marginalia,
    "context7": src_context7,
}

DEFAULT_SOURCES = [
    "bluesky",
    "hackernews",
    "github",
    "arxiv",
    "polymarket",
    "stocktwits",
    "mastodon",
    "gdelt",
]
