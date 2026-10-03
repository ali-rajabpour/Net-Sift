"""Instagram account recon via HikerAPI. Opt-in and metered: every operation is
explicitly invoked and billed per request, so it is kept apart from sweeps and
gated behind a key the user supplies (env HIKERAPI_KEY, or saved by the wizard).

Each operation estimates its cost and refuses to exceed a request cap.
"""

from __future__ import annotations

import collections
import urllib.parse
from datetime import datetime, timezone

from . import config
from .engine.core import _json

HIKER = "https://api.hikerapi.com"


class RequestCapReached(RuntimeError):
    pass


class Budget:
    """HikerAPI bills per request. Every call goes through here so a runaway
    pagination loop costs a refusal instead of the user's balance."""

    def __init__(self, cap: int):
        self.cap = cap
        self.used = 0

    def get(self, path: str, key: str, **params):
        if self.used >= self.cap:
            raise RequestCapReached(
                f"request cap reached ({self.cap}); raise max_requests to allow more"
            )
        self.used += 1
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
        return _json(f"{HIKER}{path}?{qs}", {"x-access-key": key})


def _ig_ts(x: dict):
    for k in ("taken_at", "taken_at_timestamp", "device_timestamp"):
        v = x.get(k)
        if isinstance(v, (int, float)) and v > 1_000_000_000:
            return datetime.fromtimestamp(v, timezone.utc)
    return None


def _ig_items(d, _depth: int = 0):
    """Find every media object in a HikerAPI response, wherever it is nested."""
    out = []
    if _depth > 12:
        return out
    if isinstance(d, dict):
        if "pk" in d and "code" in d and "taken_at" in d:
            return [d]
        for v in d.values():
            out += _ig_items(v, _depth + 1)
    elif isinstance(d, list):
        for v in d:
            out += _ig_items(v, _depth + 1)
    return out


def key_present() -> bool:
    return bool(config.get_secret("HIKERAPI_KEY"))


def _key():
    k = config.get_secret("HIKERAPI_KEY")
    if not k:
        raise RuntimeError(
            "no HikerAPI key; run `net-sift install` to add one, or set HIKERAPI_KEY"
        )
    return k


def _resolve(b: Budget, key: str, handle: str):
    u = b.get("/v1/user/by/username", key, username=handle.lstrip("@"))
    u = u.get("user", u) if isinstance(u, dict) else u
    uid = u.get("pk") or u.get("id")
    if not uid:
        raise RuntimeError(f"could not resolve {handle}")
    return str(uid), u


def _page(b, key, path, cursor_param, cursor_keys, item_key, limit, **params):
    out, cursor = [], None
    while len(out) < limit:
        d = b.get(path, key, **params, **({cursor_param: cursor} if cursor else {}))
        items = d.get(item_key) if isinstance(d, dict) else None
        if items is None:
            items = d if isinstance(d, list) else []
        if not items:
            break
        out += items
        cursor = next((d.get(k) for k in cursor_keys if isinstance(d, dict) and d.get(k)), None)
        if not cursor:
            break
    return out[:limit]


def _user_medias(b, key, uid, n):
    return _ig_items(
        _page(
            b,
            key,
            "/v1/user/medias/chunk",
            "end_cursor",
            ("end_cursor", "next_page_id"),
            "medias",
            n,
            user_id=uid,
        )
    )


# --- operations (return structured dicts) ---------------------------------


def op_profile(b, key, handle, **_):
    _, u = _resolve(b, key, handle)
    fields = (
        "pk",
        "username",
        "full_name",
        "follower_count",
        "following_count",
        "media_count",
        "is_private",
        "is_verified",
        "biography",
        "external_url",
        "category",
    )
    return {"profile": {f: u[f] for f in fields if u.get(f) not in (None, "")}}


def op_timeline(b, key, handle, posts=36, **_):
    uid, _ = _resolve(b, key, handle)
    when = []
    for m in _user_medias(b, key, uid, posts):
        t = _ig_ts(m)
        if t:
            when.append(t)
    if not when:
        return {"timeline": "no dated posts"}
    when.sort()
    hours = collections.Counter(d.hour for d in when)
    days = collections.Counter(d.strftime("%a") for d in when)
    span = (when[-1] - when[0]).days or 1
    gaps = [(b_ - a_).days for a_, b_ in zip(when, when[1:], strict=False)]
    return {
        "timeline": {
            "posts": len(when),
            "span_days": span,
            "per_week": round(len(when) / span * 7, 1),
            "range": [when[0].date().isoformat(), when[-1].date().isoformat()],
            "peak_hours_utc": [h for h, _ in hours.most_common(4)],
            "peak_days": [d for d, _ in days.most_common(3)],
            "median_gap_days": sorted(gaps)[len(gaps) // 2] if gaps else None,
            "longest_gap_days": max(gaps) if gaps else None,
        }
    }


def op_where(b, key, handle, posts=36, **_):
    uid, _ = _resolve(b, key, handle)
    medias = _user_medias(b, key, uid, posts)
    locs = collections.Counter()
    for m in medias:
        name = (m.get("location") or {}).get("name")
        if name:
            locs[name] += 1
    return {
        "where": {
            "geotagged": sum(locs.values()),
            "of_posts": len(medias),
            "locations": locs.most_common(12),
        }
    }


def op_fans(b, key, handle, posts=12, per_post=20, **_):
    uid, _ = _resolve(b, key, handle)
    fans, scanned = collections.Counter(), 0
    for m in _user_medias(b, key, uid, posts):
        mid = m.get("pk") or m.get("id")
        if not mid:
            continue
        try:
            d = b.get("/v1/media/comments", key, id=mid, amount=per_post)
        except RequestCapReached:
            break
        scanned += 1
        for c in d if isinstance(d, list) else d.get("comments") or []:
            u = (c.get("user") or {}).get("username")
            if u:
                fans[u] += 1
    return {"fans": {"scanned_posts": scanned, "top": fans.most_common(15)}}


def op_followers(b, key, handle, limit=200, **_):
    uid, _ = _resolve(b, key, handle)
    users = _page(
        b,
        key,
        "/v1/user/followers/chunk",
        "max_id",
        ("max_id", "next_max_id"),
        "users",
        limit,
        user_id=uid,
    )
    return {
        "followers": {
            "sampled": len(users),
            "usernames": [u.get("username", "") for u in users],
        }
    }


def op_intersect(b, key, handle, other=None, limit=200, **_):
    if not other:
        raise RuntimeError("intersect needs a second account")
    sets = {}
    for h in (handle, other):
        uid, _ = _resolve(b, key, h)
        users = _page(
            b,
            key,
            "/v1/user/followers/chunk",
            "max_id",
            ("max_id", "next_max_id"),
            "users",
            limit,
            user_id=uid,
        )
        sets[h] = {u.get("username") for u in users if u.get("username")}
    both = sorted(sets[handle] & sets[other])
    return {
        "intersect": {
            "sampled": {h: len(s) for h, s in sets.items()},
            "shared_count": len(both),
            "shared": both[:50],
            "note": "a sample of each follower list, so overlap is a lower bound",
        }
    }


OPS = {
    "profile": (op_profile, 1),
    "timeline": (op_timeline, 3),
    "where": (op_where, 3),
    "fans": (op_fans, 15),
    "followers": (op_followers, 5),
    "intersect": (op_intersect, 12),
}


def run(
    op: str,
    handle: str,
    other: str | None = None,
    posts: int = 36,
    per_post: int = 20,
    limit: int = 200,
    max_requests: int = 100,
) -> dict:
    """Run one recon operation. Returns {result..., billed_requests} or {error}."""
    if op not in OPS:
        return {"error": f"unknown op {op}; choose from {', '.join(sorted(OPS))}"}
    try:
        key = _key()
    except RuntimeError as e:
        return {"error": str(e)}
    fn, _rough = OPS[op]
    b = Budget(max_requests)
    try:
        out = fn(b, key, handle, other=other, posts=posts, per_post=per_post, limit=limit)
    except RequestCapReached as e:
        return {"error": str(e), "billed_requests": b.used}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "billed_requests": b.used}
    out["billed_requests"] = b.used
    return out
