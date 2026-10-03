"""Walled-platform access through OpenCLI (https://github.com/jackwener/opencli).

OpenCLI drives the user's real logged-in Chrome via a browser-bridge extension and
a local daemon, so login platforms are reached as the human, with no cookie
copying or private-API reverse engineering. Built-in adapters cover Twitter/X,
Reddit, Instagram, Facebook, Bilibili, Xiaohongshu, Zhihu, and more.

net-sift shells to ``opencli <site> <command> -f json`` directly and normalizes the
structured output into engine records, so the raw platform payload never reaches
the agent. Adapters are discovered at runtime via ``opencli list`` rather than
hardcoded, so net-sift tracks OpenCLI's adapter set as it changes.

Desktop-only: requires Node >= 20.18.1, the OpenCLI runtime, Chrome with the
bridge extension, and an existing logged-in session. When any of that is missing,
access degrades to a declared gap, never a crash.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone

from ..engine.core import Record, parse_iso, rec

OPENCLI_BIN = os.environ.get("NET_SIFT_OPENCLI_BIN", "opencli")

# Login platforms we route through OpenCLI. Keyless platforms (hackernews, etc.)
# stay in the engine even though OpenCLI also offers them.
# Login platforms we route through OpenCLI, each mapped to its search command (all
# verified to expose `search` in the OpenCLI adapter catalog). OpenCLI uses the id
# `twitter` for X. Keyless platforms (hackernews, etc.) stay in the engine.
WALLED_SEARCH = {
    "twitter": "search",
    "reddit": "search",
    "instagram": "search",
    "facebook": "search",
    "bilibili": "search",
    "xiaohongshu": "search",
    "zhihu": "search",
}
WALLED_SITES = tuple(WALLED_SEARCH)

# Friendly name + login URL per platform, for the setup wizard.
WALLED_META = {
    "twitter": ("X (Twitter)", "https://x.com"),
    "reddit": ("Reddit", "https://www.reddit.com"),
    "instagram": ("Instagram", "https://www.instagram.com"),
    "facebook": ("Facebook", "https://www.facebook.com"),
    "bilibili": ("Bilibili", "https://www.bilibili.com"),
    "xiaohongshu": ("Xiaohongshu (RED)", "https://www.xiaohongshu.com"),
    "zhihu": ("Zhihu", "https://www.zhihu.com"),
}


class OpenCLIUnavailable(RuntimeError):
    pass


def binary() -> str | None:
    return shutil.which(OPENCLI_BIN)


def doctor_text(timeout: int = 30) -> str | None:
    """Run ``opencli doctor``. This both STARTS the daemon (it only auto-starts on
    an opencli command) and reports connectivity. None when the binary is absent or
    the call fails. Takes a few seconds, so callers that run often should use
    ``available_cached``."""
    exe = binary()
    if not exe:
        return None
    try:
        p = subprocess.run([exe, "doctor"], capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return None


def _parse_connected(text: str | None) -> bool:
    if not text:
        return False
    low = text.lower()
    return "connectivity: connected" in low or "extension: connected" in low


def available() -> bool:
    """True when opencli is installed and a browser session is connected. Runs
    ``opencli doctor``, which starts the daemon if needed, so calling this is also
    what brings a freshly installed OpenCLI online."""
    return _parse_connected(doctor_text())


def available_cached(ttl: int = 60) -> bool:
    """available() with a short on-disk cache, for frequent callers (status bar)."""
    from .. import config

    cache = config.HOME / ".opencli_status"
    try:
        d = json.loads(cache.read_text())
        if time.time() - d.get("ts", 0) < ttl:
            return bool(d.get("available"))
    except (OSError, ValueError):
        pass
    val = available()
    try:
        config.HOME.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"ts": time.time(), "available": val}))
    except OSError:
        pass
    return val


def status(connected: bool | None = None) -> str:
    """One-line, secret-free summary for the doctor. Pass `connected` to reuse a
    single connectivity check instead of running `opencli doctor` again."""
    if not binary():
        return "opencli: not installed (npm i -g @jackwener/opencli, or OpenCLIApp)"
    if connected is None:
        connected = available()
    if connected:
        return "opencli: connected"
    return (
        "opencli: installed, no browser session connected (open a Chromium browser "
        "with the OpenCLI extension and log in; the daemon starts automatically)"
    )


def run(
    site: str,
    command: str,
    *args: str,
    fmt: str = "json",
    limit: int | None = None,
    timeout: int = 90,
):
    """Run ``opencli <site> <command> [args] -f json`` and return parsed output."""
    exe = binary()
    if not exe:
        raise OpenCLIUnavailable("opencli binary not found")
    cmd = [exe, site, command, *args, "-f", fmt]
    if limit is not None:
        cmd += ["--limit", str(limit)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        raise OpenCLIUnavailable(f"opencli invocation failed: {e}") from e
    if proc.returncode != 0:
        raise OpenCLIUnavailable(
            f"opencli {site} {command} exit {proc.returncode}: {proc.stderr.strip()[:200]}"
        )
    out = proc.stdout.strip()
    if not out:
        return []
    try:
        return json.loads(out)
    except ValueError as e:
        raise OpenCLIUnavailable(f"opencli {site} {command}: non-JSON output") from e


def discover() -> dict[str, list[str]]:
    """Map site -> [commands] from ``opencli list``. Empty when unavailable."""
    exe = binary()
    if not exe:
        return {}
    try:
        proc = subprocess.run(
            [exe, "list", "-f", "json"], capture_output=True, text=True, timeout=30
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return _parse_list_json(proc.stdout)
    except (OSError, subprocess.SubprocessError):
        pass
    # Fall back to the plain-text listing shape ("site command  - description").
    try:
        proc = subprocess.run([exe, "list"], capture_output=True, text=True, timeout=30)
        return _parse_list_text(proc.stdout) if proc.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError):
        return {}


def _parse_list_json(text: str) -> dict[str, list[str]]:
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    out: dict[str, list[str]] = {}
    items = data if isinstance(data, list) else data.get("commands", [])
    for it in items:
        if not isinstance(it, dict):
            continue
        site = it.get("site") or it.get("namespace") or it.get("group")
        command = it.get("command") or it.get("name") or it.get("action")
        if site and command:
            out.setdefault(site, []).append(command)
    return out


def _parse_list_text(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].isidentifier():
            out.setdefault(parts[0], []).append(parts[1])
    return out


# --- normalization --------------------------------------------------------

_ID_KEYS = ("id", "rest_id", "note_id", "aweme_id", "pk", "objectID", "url")
_URL_KEYS = ("url", "link", "permalink", "share_url", "webpage_url", "href")
_TEXT_KEYS = (
    "text",
    "full_text",
    "content",
    "caption",
    "caption_text",
    "body",
    "desc",
    "description",
    "summary",
    "title",
)
_CREATED_KEYS = (
    "created_at",
    "createdAt",
    "created_utc",
    "timestamp",
    "taken_at",
    "published",
    "date",
    "time",
)
_ENGAGEMENT = {
    "likes": ("likes", "like_count", "favorite_count", "digg_count", "favoriteCount"),
    "comments": ("comments", "comment_count", "reply_count", "replies", "commentCount"),
    "reposts": ("reposts", "retweet_count", "share_count", "shares", "forwards"),
    "views": ("views", "play_count", "view_count", "viewCount"),
    "score": ("score", "points", "upvotes", "ups"),
}


def _first(d: dict, keys) -> object:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def _author(d: dict) -> str | None:
    for k in ("author", "username", "screen_name", "handle", "uploader", "nickname", "name"):
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
    for k in ("user", "owner", "account"):
        u = d.get(k)
        if isinstance(u, dict):
            for kk in ("screen_name", "username", "name", "nickname", "unique_id"):
                if u.get(kk):
                    return u[kk]
    return None


def _created(d: dict) -> str | None:
    v = _first(d, _CREATED_KEYS)
    if v is None:
        return None
    if isinstance(v, (int, float)) and v > 1_000_000_000:
        return datetime.fromtimestamp(v, timezone.utc).isoformat()
    if isinstance(v, str):
        return v
    return None


def _text(d: dict) -> str:
    parts = []
    for k in ("title",):
        if isinstance(d.get(k), str) and d[k]:
            parts.append(d[k])
    body = _first(d, [k for k in _TEXT_KEYS if k != "title"])
    if isinstance(body, dict):
        body = body.get("text") or ""
    if isinstance(body, str) and body and body not in parts:
        parts.append(body)
    return "\n".join(parts)


def normalize(item: dict, site: str) -> Record | None:
    if not isinstance(item, dict):
        return None
    ident = _first(item, _ID_KEYS)
    text = _text(item)
    if ident is None and not text:
        return None
    extra = {}
    for field, keys in _ENGAGEMENT.items():
        v = _first(item, keys)
        if isinstance(v, (int, float)):
            extra[field] = v
    return rec(
        site,
        ident or abs(hash(text)) % 10**12,
        _first(item, _URL_KEYS) or "",
        _author(item),
        text,
        _created(item),
        extra,
    )


def _items(payload) -> list[dict]:
    """Find the list of result objects in whatever envelope the adapter returns."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for k in ("results", "data", "items", "notes", "tweets", "posts", "list"):
            v = payload.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def make_source(site: str, command: str):
    """Build an engine source that searches one walled platform via OpenCLI."""

    def source(query, since, until, budget):
        payload = run(site, command, query, limit=min(budget, 100))
        out: list[Record] = []
        for item in _items(payload)[:budget]:
            r = normalize(item, site)
            if not r:
                continue
            when = parse_iso(r.get("created_at"))
            if when and since and when < since:
                continue
            if when and until and when > until:
                continue
            out.append(r)
        return out, False

    source.__name__ = f"opencli_{site}"
    return source


def _probe_once(site: str, timeout: int) -> tuple[bool, str]:
    exe = binary()
    if not exe:
        return False, "no-opencli"
    try:
        p = subprocess.run(
            [exe, site, "search", "news", "--limit", "1", "-f", "json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return False, "error"
    blob = (p.stdout or "") + (p.stderr or "")
    if "navigation rejected" in blob.lower():
        return False, "blocked"
    if p.returncode != 0 or not p.stdout.strip():
        return False, "login"
    try:
        d = json.loads(p.stdout)
    except ValueError:
        return False, "error"
    if isinstance(d, dict) and d.get("ok") is False:
        msg = str((d.get("error") or {}).get("message", "")).lower()
        return False, ("blocked" if "navigation rejected" in msg else "login")
    return True, "ok"


def probe_detail(site: str, timeout: int = 60, attempts: int = 2) -> tuple[bool, str]:
    """Probe a platform with a real search. Returns (connected, reason):
      (True, "ok")         - search worked, so the browser is logged in and usable
      (False, "blocked")   - OpenCLI could not open the site (anti-automation block
                             or a broken adapter); logging in will NOT fix this
      (False, "login")     - reachable but the search failed; a login may help
      (False, "no-opencli"/"error") - opencli missing or an unexpected failure

    Retries transient failures: the first browser command after the daemon starts
    is often flaky, so a logged-in account can falsely read as not connected on a
    single try. A "blocked" or "no-opencli" result is definitive and not retried.
    """
    ok, reason = _probe_once(site, timeout)
    for _ in range(max(0, attempts - 1)):
        if ok or reason in ("blocked", "no-opencli"):
            break
        time.sleep(2)
        ok, reason = _probe_once(site, timeout)
    return ok, reason


def probe_login(site: str, timeout: int = 60) -> bool:
    """True when a real search on `site` works, i.e. the browser is logged into it."""
    return probe_detail(site, timeout=timeout)[0]


def walled_sources(connected: bool | None = None) -> dict[str, object]:
    """Build a search source per walled platform, when a browser session is
    connected. Uses the verified WALLED_SEARCH map rather than parsing `opencli
    list`, so it is deterministic. Pass `connected` to reuse one connectivity check."""
    if connected is None:
        connected = available()
    if not connected:
        return {}
    return {site: make_source(site, cmd) for site, cmd in WALLED_SEARCH.items()}
