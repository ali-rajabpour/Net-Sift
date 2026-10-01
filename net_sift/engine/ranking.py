#!/usr/bin/env python3
"""Query-centric relevance ranking for the Net-Sift engine.

Three ideas, ported and trimmed from mvanhorn/last30days-skill (MIT):

  1. Token-overlap relevance with a phrase bonus and a stopword list, so a match
     on generic words alone ("review", "odds") never reads as on-topic.
  2. Entity grounding on the *head* token of the query - trailing words are
     usually descriptors ("tron blockchain review" is about tron), so requiring
     the whole phrase falsely demotes on-entity items. A grounding miss is a
     decisive demotion that engagement cannot rescue; its failure modes degrade
     toward "no penalty", never toward burying real signal.
  3. CJK segmentation: Chinese has no whitespace, so str.split collapses a whole
     sentence into one token and overlap scoring dies. segment() splits CJK runs
     via jieba when present, else character bigrams (dictionary-free, still a
     robust overlap signal).

Recency is kept as a *boost*, never a hard window (Ali's call): a decaying
multiplier on the final score, not a filter that drops old items.

Zero third-party deps. jieba is used only if already importable.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone

# --- CJK segmentation -----------------------------------------------------

# Chinese ideographs + ext-A, compatibility ideographs, kana, hangul. Enough to
# route CJK sources (Xiaohongshu, V2EX, Sogou/WeChat) through real segmentation
# and let mixed-language text degrade gracefully.
_CJK = r"㐀-䶿一-鿿豈-﫿぀-ヿ가-힯"
_CJK_RUN = re.compile(f"[{_CJK}]+")
_LATIN = re.compile(r"\w+", re.UNICODE)

CHINESE_STOPWORDS = frozenset(
    "的 了 和 是 在 我 有 也 就 不 人 都 一 一个 上 很 到 说 要 去 你 会 着 "
    "没有 看 好 自己 这 那 与 及 或 等 中 为 对 以 从 但".split()
)

STOPWORDS = (
    frozenset(
        "the a an to for how is in of on and with from by at this that it my your i "
        "me we you what are do can its be or not no so if but about all just get has "
        "have was will who whom which when where why".split()
    )
    | CHINESE_STOPWORDS
)

try:  # optional: better Chinese segmentation if the user has it, never required
    import jieba as _jieba  # type: ignore

    _jieba.setLogLevel(60)
except Exception:  # pragma: no cover - depends on host
    _jieba = None


def _cjk_tokens(run: str) -> list[str]:
    if _jieba is not None:
        return [w for w in _jieba.cut(run) if w.strip()]
    # character bigrams: "大模型" -> {大模, 模型}. A single char stays as-is so
    # one-character queries still match.
    if len(run) == 1:
        return [run]
    return [run[i : i + 2] for i in range(len(run) - 1)]


def segment(text: str) -> list[str]:
    """Split into maximal CJK and Latin runs; tokenize each in its own idiom."""
    if not text:
        return []
    out: list[str] = []
    i, n = 0, len(text)
    for m in _CJK_RUN.finditer(text):
        if m.start() > i:
            out += _LATIN.findall(text[i : m.start()].lower())
        out += _cjk_tokens(m.group())
        i = m.end()
    if i < n:
        out += _LATIN.findall(text[i:].lower())
    return out


def content_tokens(text: str) -> list[str]:
    """Segment, lowercase, drop stopwords and 1-char Latin noise (CJK bigrams kept)."""
    toks = []
    for t in segment(text):
        if t in STOPWORDS:
            continue
        if t.isascii() and len(t) < 2:
            continue
        toks.append(t)
    return toks


# --- relevance ------------------------------------------------------------

RELEVANCE_FLOOR = 0.1  # below this an item is off-topic
MIN_ON_TOPIC = 5  # only apply the floor wholesale once this many clear it
GROUNDING_MISS = 0.05  # decisive multiplier when the head entity is absent


def relevance(query: str, text: str) -> float:
    """0..1 query-centric overlap. Exact phrase -> 1.0; else fraction of distinct
    query content-tokens present in the text."""
    if not query:
        return 1.0
    if not text:
        return 0.0
    q = list(dict.fromkeys(content_tokens(query)))  # distinct, order-stable
    if not q:
        return 1.0  # query was all stopwords; nothing to discriminate on
    ql = query.strip().lower()
    if len(ql) >= 3 and ql in text.lower():
        return 1.0
    t = set(content_tokens(text))
    if not t:
        return 0.0
    hits = sum(1 for w in q if w in t)
    return hits / len(q)


def head_token(query: str) -> str | None:
    """First content token - the query's primary entity head."""
    toks = content_tokens(query)
    return toks[0] if toks else None


def grounded(query: str, text: str) -> bool:
    """Does the text plausibly mention the query's head entity?"""
    head = head_token(query)
    if not head:
        return True
    return head in set(content_tokens(text))


def recency_boost(created_at, now=None, half_life_days: float = 30.0) -> float:
    """Decaying 0..1 boost. Undated items get a neutral 0.5 rather than a penalty."""
    if not created_at:
        return 0.5
    when = _parse(created_at)
    if not when:
        return 0.5
    now = now or datetime.now(timezone.utc)
    age = max(0.0, (now - when).total_seconds() / 86400.0)
    return math.exp(-age / half_life_days) if half_life_days > 0 else 0.0


_ENGAGEMENT_KEYS = (
    "likes",
    "score",
    "points",
    "retweets",
    "reposts",
    "replies",
    "comments",
    "num_comments",
    "views",
    "quotes",
    "stars",
)


def engagement(rec: dict) -> float:
    """Log-scaled 0..1 from whatever engagement fields the record carries."""
    total = 0
    for k in _ENGAGEMENT_KEYS:
        v = rec.get(k)
        if isinstance(v, (int, float)) and v > 0:
            total += v
    if total <= 0:
        return 0.0
    return min(1.0, math.log1p(total) / math.log1p(100_000))


def score(rec: dict, query: str, now=None) -> float:
    """Combined ranking score. Relevance dominates; recency and engagement modulate."""
    rel = rec.get("_relevance")
    if rel is None:
        rel = relevance(query, rec.get("text", ""))
    return rel * (1.0 + 0.30 * recency_boost(rec.get("created_at"), now) + 0.20 * engagement(rec))


def rank(records: list[dict], query: str, now=None, floor: float = RELEVANCE_FLOOR):
    """Score, ground, drop the off-topic tail, sort best-first.

    Annotates each record with `_relevance` and `_score`. Returns (ranked, dropped).
    """
    now = now or datetime.now(timezone.utc)
    for r in records:
        rel = relevance(query, r.get("text", ""))
        if not grounded(query, r.get("text", "")):
            rel *= GROUNDING_MISS
        r["_relevance"] = round(rel, 4)
        r["_score"] = round(score(r, query, now), 4)
    on_topic = [r for r in records if r["_relevance"] >= floor]
    kept = on_topic if len(on_topic) >= MIN_ON_TOPIC else records
    dropped = len(records) - len(kept)
    kept.sort(key=lambda r: r["_score"], reverse=True)
    return kept, dropped


def _parse(s):
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    if not isinstance(s, str):
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def demo():
    """Runnable checks for the logic that would silently rot: overlap, grounding,
    CJK segmentation, the floor, and recency-as-boost-not-filter."""
    # phrase + all-terms vs OR-match noise
    assert relevance("tron blockchain", "TRON blockchain upgrade shipped") == 1.0
    assert relevance("tron blockchain", "my blockchain course review") < 0.6
    assert relevance("tron blockchain", "tron blockchain") == 1.0

    # grounding: head entity missing -> decisive demotion, present -> intact
    recs = [
        {"text": "tron blockchain news", "created_at": None},  # grounded, on-topic
        {"text": "generic blockchain tutorial", "created_at": None},  # head 'tron' absent
    ]
    ranked, _ = rank(list(recs), "tron blockchain", floor=0.0)
    assert ranked[0]["text"].startswith("tron"), "grounded item must rank first"
    assert ranked[1]["_relevance"] < 0.1, "grounding miss must be decisive"

    # CJK: bigram/jieba segmentation makes overlap work on Chinese
    assert relevance("大模型", "国产大模型评测") > 0.0, "CJK overlap must fire"
    assert segment("大模型评测") != ["大模型评测"], "CJK must not collapse to one token"

    # floor drops the zero-overlap tail only when enough on-topic items remain
    many = [{"text": "tron update", "created_at": None} for _ in range(6)]
    many += [{"text": "totally unrelated cats", "created_at": None}]
    kept, dropped = rank(many, "tron")
    assert dropped == 1, f"floor should drop the 1 off-topic item, dropped {dropped}"

    # recency is a boost, never a filter: an old on-topic item is still kept
    old = [{"text": "tron launch", "created_at": "2009-01-03T00:00:00Z"}]
    kept, dropped = rank(old, "tron")
    assert dropped == 0 and kept, "old on-topic item must survive (boost, not window)"

    # engagement lifts ties but cannot rescue an off-entity item
    tie = [
        {"text": "tron", "created_at": None, "likes": 0},
        {"text": "tron", "created_at": None, "likes": 50_000},
    ]
    kept, _ = rank(tie, "tron", floor=0.0)
    assert kept[0]["likes"] == 50_000, "engagement should break a relevance tie"
    print("ranking.demo ok")


if __name__ == "__main__":
    demo()
