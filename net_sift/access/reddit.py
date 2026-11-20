"""Reddit search, scraped from its HTML search page in the managed browser.

Reddit answers every JSON endpoint (/search.json, /svc/shreddit/search, the OAuth
API) with a 403 "blocked by network security" page, for any client. The HTML
search page still works, but only for a session a human signed into by hand, in a
browser whose user agent matches its real version. A fresh profile, or one with old
copied cookies ("Prove your humanity"), is blocked. That is reported as a gap with
the fix (`net-sift login reddit`), never worked around.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from html.parser import HTMLParser

from ..engine.core import Record, parse_iso, rec
from . import browser, opencli, profile

BASE = "https://www.reddit.com"
GAP = "reddit session blocked/expired: run `net-sift login reddit` and sign in by hand"

_VOID = set("area base br col embed hr img input link meta source wbr".split())


class RedditBlocked(RuntimeError):
    pass


def blocked(title: str, text: str) -> bool:
    """Reddit's block page for a missing or stale session."""
    return bool(
        re.search(r"prove your humanity", title, re.I) or re.search(r"network security", text, re.I)
    )


def _iso(ts: str | None) -> str | None:
    if not ts:
        return None
    ts = re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", ts)  # +0000 -> +00:00 for Python 3.10
    d = parse_iso(ts)
    return d.isoformat() if d else None


class _Results(HTMLParser):
    """Collect search results. Each result is a tree of search-telemetry-tracker
    elements sharing one post context (post.id, post.title, profile.name,
    subreddit.name, nsfw); the title link, timestamp, vote and comment counts and
    the body snippet sit inside that tree."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.posts: dict[str, dict] = {}
        self._stack: list[tuple[str, str | None, str | None]] = []  # (tag, post id, role)

    def _post(self) -> dict | None:
        pid = next((p for _, p, _ in reversed(self._stack) if p), None)
        return self.posts.get(pid) if pid else None

    def _in(self, role: str) -> bool:
        return any(r == role for _, _, r in self._stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        pid = role = None
        if tag == "search-telemetry-tracker":
            try:
                ctx = json.loads(a.get("data-faceplate-tracking-context") or "{}")
            except ValueError:
                ctx = {}
            post = ctx.get("post") or {}
            if post.get("id") and post.get("title"):
                pid = post["id"]
                self.posts.setdefault(
                    pid,
                    {
                        "id": pid.removeprefix("t3_"),
                        "title": post["title"],
                        "author": (ctx.get("profile") or {}).get("name"),
                        "subreddit": (ctx.get("subreddit") or {}).get("name"),
                        "nsfw": bool(post.get("nsfw")),
                        "href": None,
                        "created": None,
                        "counts": [],
                        "snippet": [],
                    },
                )
                if (ctx.get("action_info") or {}).get("type") == "snippet":
                    role = "snippet"
        elif a.get("data-testid") == "search-counter-row":
            role = "counter"
        cur = self._post()
        if cur is not None:
            if tag == "a" and a.get("data-testid") == "post-title" and not cur["href"]:
                cur["href"] = a.get("href")
            elif tag == "faceplate-timeago" and not cur["created"]:
                cur["created"] = a.get("ts")
            elif tag == "faceplate-number" and self._in("counter"):
                cur["counts"].append(a.get("number"))
        if tag not in _VOID:
            self._stack.append((tag, pid, role))

    def handle_endtag(self, tag):
        if any(t == tag for t, _, _ in self._stack):
            while self._stack and self._stack.pop()[0] != tag:
                pass

    def handle_data(self, data):
        cur = self._post()
        if cur is not None and self._in("snippet") and data.strip():
            cur["snippet"].append(data.strip())


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse(html: str) -> list[Record]:
    """Records from a rendered Reddit search page, in page order."""
    p = _Results()
    p.feed(html)
    out = []
    for post in p.posts.values():
        href = post["href"] or f"/comments/{post['id']}/"
        extra = {"subreddit": post["subreddit"], "nsfw": post["nsfw"]}
        for field, v in zip(("score", "comments"), post["counts"], strict=False):
            if _int(v) is not None:
                extra[field] = _int(v)
        text = "\n".join([post["title"], " ".join(post["snippet"])]).strip()
        out.append(
            rec(
                "reddit",
                post["id"],
                urllib.parse.urljoin(BASE, href),
                post["author"],
                text,
                _iso(post["created"]),
                extra,
            )
        )
    return out


def search_url(query: str, subreddit: str | None = None, sort: str = "new", t: str = "") -> str:
    q = {"q": query, "type": "posts", "sort": sort}
    if t:
        q["t"] = t
    if subreddit:
        q["restrict_sr"] = "1"
        return f"{BASE}/r/{subreddit}/search/?{urllib.parse.urlencode(q)}"
    return f"{BASE}/search/?{urllib.parse.urlencode(q)}"


_STATE = (
    "JSON.stringify({ready: document.readyState, title: document.title,"
    " text: (document.body && document.body.innerText || '').slice(0, 3000),"
    " n: document.querySelectorAll('a[data-testid=\"post-title\"]').length,"
    " last: ([...document.querySelectorAll('faceplate-timeago[ts]')].pop() || {getAttribute: () => null}).getAttribute('ts')})"
)


def _state(page: browser.Page) -> dict:
    return json.loads(page.eval(_STATE) or "{}")


def _settle(page: browser.Page, grew_from: int = -1, wait: float = 9.0) -> dict:
    """Poll until the page is loaded and shows results (or more results than
    `grew_from`), is blocked, or `wait` runs out. Hydration takes several seconds."""
    deadline = time.time() + wait
    while True:
        time.sleep(1)
        st = _state(page)
        if blocked(st.get("title", ""), st.get("text", "")):
            raise RedditBlocked(GAP)
        if st.get("ready") == "complete" and st.get("n", 0) > max(grew_from, 0):
            return st
        if time.time() > deadline:
            return st


# ponytail: at most 20 scrolls (~180 posts) per query; raise it if deep Reddit
# history matters more than sweep time.
MAX_SCROLLS = 20


def search(query, since, until, budget) -> tuple[list[Record], bool]:
    """Engine source. Needs the managed browser of the current sweep."""
    endpoint = opencli.current_endpoint()
    if not endpoint:
        raise RedditBlocked("reddit needs the managed browser; run `net-sift install`")
    # Held for the whole visit: an OpenCLI command can attach to any open tab.
    with opencli._run_lock, browser.Page(endpoint, search_url(query)) as page:
        st = _settle(page, wait=15)
        for _ in range(MAX_SCROLLS):
            old = st.get("last")
            if st.get("n", 0) >= budget or (since and old and parse_iso(_iso(old)) < since):
                break
            page.eval("window.scrollTo(0, document.body.scrollHeight)")
            nxt = _settle(page, grew_from=st.get("n", 0), wait=6)
            if nxt.get("n", 0) <= st.get("n", 0):
                break  # nothing more loaded
            st = nxt
        html = page.eval("document.documentElement.outerHTML") or ""
    out = []
    for r in parse(html):
        when = parse_iso(r.get("created_at"))
        if when and ((since and when < since) or (until and when > until)):
            continue
        out.append(r)
    return out[:budget], False


def status(endpoint: str, profile_dir: str) -> str:
    """One search page load: "live (N results)", "blocked", or "needs-login"."""
    if not profile.logged_in(profile_dir).get("reddit"):
        return "needs-login"
    with browser.Page(endpoint, search_url("news")) as page:
        try:
            st = _settle(page, wait=15)
        except RedditBlocked:
            return "blocked"
    n = st.get("n", 0)
    return f"live ({n} results)" if n else "no results: the page loaded but showed no posts"
