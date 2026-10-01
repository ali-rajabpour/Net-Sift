from datetime import timedelta

from net_sift.engine import core


def _rec(source, ident, text):
    return core.rec(source, ident, "u", "a", text, None)


def test_dedup_exact_id():
    rows = [_rec("s", "1", "hello world")] * 3
    assert len(core.dedup(rows)) == 1


def test_dedup_near_duplicate_same_source():
    rows = [
        _rec("reddit", "1", "just shipped a tool that turns notes into a searchable index offline"),
        _rec(
            "reddit",
            "2",
            "just shipped a tool that turns notes into a searchable index offline today",
        ),
    ]
    assert len(core.dedup(rows, near_dup=0.85)) == 1
    assert len(core.dedup(rows, near_dup=0)) == 2  # disabled


def test_dedup_keeps_cross_source():
    rows = [
        _rec("hackernews", "1", "I built obsidian from scratch over the weekend here"),
        _rec("reddit", "2", "I built obsidian from scratch over the weekend here"),
    ]
    assert len(core.dedup(rows)) == 2  # same story on two platforms is a coverage finding


def test_dedup_short_posts_not_near_collapsed():
    rows = [_rec("x", "1", "this is fine"), _rec("x", "2", "this is fine too")]
    assert len(core.dedup(rows)) == 2


def test_collect_bisects_on_ceiling():
    calls = []

    def fake(query, since, until, budget):
        calls.append((since, until))
        span = (until - since).days
        recs = [
            _rec("fake", str((since + timedelta(days=i)).date()), "t") for i in range(min(span, 2))
        ]
        return recs, span > 2

    recs, _ = core.collect(
        fake, "fake", "q", core.parse_day("2026-01-01"), core.parse_day("2026-01-09"), 100
    )
    ids = {r["id"] for r in recs}
    assert len(calls) > 1  # bisection fired
    assert len(ids) >= 8  # recovered the hidden tail
