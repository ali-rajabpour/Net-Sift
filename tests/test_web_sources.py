import json
from datetime import datetime, timezone

import pytest

from net_sift import search
from net_sift.access import opencli
from net_sift.engine import sources

SINCE = datetime(2026, 9, 1, tzinfo=timezone.utc)
UNTIL = datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_open_sources_gating(monkeypatch):
    monkeypatch.setattr(opencli, "binary", lambda: None)
    assert opencli.open_sources(connected=True) == {}

    monkeypatch.setattr(opencli, "binary", lambda: "/usr/bin/opencli")
    assert set(opencli.open_sources(connected=True)) == set(opencli.OPEN_SEARCH)
    public = opencli.open_sources(connected=False)
    assert "wikipedia" in public and "google_news" in public
    assert "google" not in public and "youtube" not in public  # these need the browser


def test_normalize_string_counts_and_dates():
    so = opencli.normalize(
        {"id": "1", "title": "Q", "views": "161", "answers": "1", "creation_date": "1458266412"},
        "stackoverflow",
    )
    assert so["views"] == 161 and so["comments"] == 1
    assert so["created_at"].startswith("2016-03-18")

    yt = opencli.normalize(
        {"title": "T", "url": "u", "channel": "C", "views": "2,567,631 views"}, "youtube"
    )
    assert yt["views"] == 2567631 and yt["author"] == "C"

    news = opencli.normalize(
        {"title": "T", "url": "u", "source": "CNN", "date": "Sat, 03 Oct 2026 10:30:46 GMT"},
        "google_news",
    )
    assert news["created_at"].startswith("2026-10-03T10:30:46")

    wd = opencli.normalize({"qid": "Q1", "label": "climate", "description": "d"}, "wikidata")
    assert wd["text"] == "climate\nd"


def test_make_source_retries_rejected_navigation(monkeypatch):
    calls = []

    def fake_run(site, command, query, limit=None):
        calls.append(limit)
        if len(calls) < 3:
            raise opencli.OpenCLIUnavailable("opencli google search exit 1: Navigation rejected.")
        return [{"title": "t", "url": "https://example.org", "snippet": "s"}]

    monkeypatch.setattr(opencli, "run", fake_run)
    monkeypatch.setattr(opencli.time, "sleep", lambda s: None)
    recs, ceiling = opencli.make_source("google", "search", "google", 10)("q", None, None, 500)
    assert calls == [10, 10, 10]  # capped at the adapter limit, third try passes
    assert recs[0]["source"] == "google" and ceiling is False


def test_make_source_retries_transient_cdp_error(monkeypatch):
    calls = []

    def fake_run(site, command, query, limit=None):
        calls.append(1)
        if len(calls) < 2:
            raise opencli.OpenCLIUnavailable("opencli tiktok search exit 1: UNKNOWN CDP command")
        return [{"title": "t", "url": "u"}]

    monkeypatch.setattr(opencli, "run", fake_run)
    monkeypatch.setattr(opencli.time, "sleep", lambda s: None)
    recs, _ = opencli.make_source("tiktok", "search")("q", None, None, 10)
    assert len(calls) == 2 and recs[0]["source"] == "tiktok"


def test_make_source_does_not_retry_other_errors(monkeypatch):
    def fake_run(site, command, query, limit=None):
        raise opencli.OpenCLIUnavailable("opencli binary not found")

    monkeypatch.setattr(opencli, "run", fake_run)
    with pytest.raises(opencli.OpenCLIUnavailable):
        opencli.make_source("google", "search")("q", None, None, 10)


def test_telegram_channels():
    urls = [
        "https://t.me/s/BitcoinBullets?before=17307",
        "https://t.me/Cryptocurrency_Inside",
        "https://t.me/s/BitcoinBullets",
        "https://t.me/joinchat/AAAA",
        "https://example.org/t.me/nope",
        "",
    ]
    assert sources.telegram_channels(urls) == ["BitcoinBullets", "Cryptocurrency_Inside"]


def test_discover_telegram_uses_google():
    seen = []

    def google(query, since, until, budget):
        seen.append(query)
        return [{"url": "https://t.me/s/chan_one"}, {"url": "https://bitcoin.org"}], False

    assert search.discover_telegram("bitcoin", {"google": google}) == ["chan_one"]
    assert seen == ["site:t.me subscribers bitcoin"]


def test_brave_pages_until_exhausted(monkeypatch):
    calls = []

    def fake_json(url, headers=None):
        calls.append((url, headers))
        last = len(calls) == 2
        n = 5 if last else sources.BRAVE_PAGE
        results = [
            {"url": f"https://e.org/{len(calls)}/{i}", "title": "t", "description": "d"}
            for i in range(n)
        ]
        return {"web": {"results": results}, "query": {"more_results_available": not last}}

    monkeypatch.setattr(sources, "_json", fake_json)
    recs, ceiling = sources.src_brave("q", SINCE, UNTIL, 2000, key="k")
    assert len(recs) == 25 and ceiling is False
    assert len(calls) == 2  # stops when the API says there is no more
    assert "offset=1" in calls[1][0] and "freshness=2026-09-01to2026-10-01" in calls[0][0]
    assert calls[0][1]["X-Subscription-Token"] == "k"


def test_brave_never_exceeds_ten_requests(monkeypatch):
    calls = []

    def fake_json(url, headers=None):
        calls.append(url)
        results = [{"url": f"https://e.org/{len(calls)}/{i}"} for i in range(sources.BRAVE_PAGE)]
        return {"web": {"results": results}, "query": {"more_results_available": True}}

    monkeypatch.setattr(sources, "_json", fake_json)
    recs, _ = sources.src_brave("q", None, None, 100000, key="k")
    assert len(calls) == sources.BRAVE_MAX_PAGES and len(recs) == 200


def test_brave_needs_key(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        sources.src_brave("q", None, None, 10)


def test_brave_and_ddg_are_browser_sources():
    assert opencli.OPEN_SEARCH["brave"] == ("brave", "search", 18, True)
    assert opencli.OPEN_SEARCH["duckduckgo"] == ("duckduckgo", "search", 10, True)


def test_context7_parses_snippets(monkeypatch):
    payload = {
        "codeSnippets": [
            {
                "libraryId": "/vercel/next.js",
                "codeTitle": "stream",
                "codeList": [{"code": "await x"}],
            }
        ],
        "infoSnippets": [{"libraryId": "/openai/openai", "content": "Use the SDK"}],
    }
    monkeypatch.setattr(sources, "_json", lambda url, headers=None: payload)
    recs, ceiling = sources.src_context7("stream openai", None, None, 10, key="k")
    assert ceiling is False and len(recs) == 2
    assert recs[0]["source"] == "context7"
    assert "await x" in recs[0]["text"]
    assert recs[0]["url"] == "https://context7.com/vercel/next.js"


def test_context7_needs_key(monkeypatch):
    monkeypatch.delenv("CONTEXT7_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        sources.src_context7("q", None, None, 10)


def test_firecrawl_posts_and_parses(monkeypatch):
    seen = {}

    def fake_json(url, headers=None, data=None):
        seen["url"] = url
        seen["auth"] = headers.get("Authorization")
        seen["body"] = json.loads(data)
        return {
            "success": True,
            "data": {"web": [{"url": "https://e.org", "title": "t", "description": "d"}]},
        }

    monkeypatch.setattr(sources, "_json", fake_json)
    recs, ceiling = sources.src_firecrawl("google blocked thing", SINCE, UNTIL, 2000, key="fc-k")
    assert ceiling is False and recs[0]["source"] == "firecrawl"
    assert recs[0]["url"] == "https://e.org" and "t\nd" == recs[0]["text"]
    assert seen["url"] == "https://api.firecrawl.dev/v2/search"
    assert seen["auth"] == "Bearer fc-k"
    assert seen["body"]["query"] == "google blocked thing" and seen["body"]["limit"] == 100
    assert "cd_min:09/01/2026" in seen["body"]["tbs"]


def test_firecrawl_needs_key(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        sources.src_firecrawl("q", None, None, 10)


def test_gdelt_ceiling_and_plain_text_error(monkeypatch):
    arts = [
        {"url": f"https://n.org/{i}", "title": "t", "seendate": "20260915T101500Z", "domain": "n"}
        for i in range(250)
    ]
    monkeypatch.setattr(
        sources, "_get", lambda url, headers=None: json.dumps({"articles": arts}).encode()
    )
    recs, ceiling = sources.src_gdelt("q", SINCE, UNTIL, 2000)
    assert len(recs) == 250 and ceiling is True  # a full page makes the driver bisect
    assert recs[0]["created_at"] == "2026-09-15T10:15:00+00:00"

    monkeypatch.setattr(sources, "_get", lambda url, headers=None: b"{}")
    assert sources.src_gdelt("q", SINCE, UNTIL, 2000) == ([], False)

    monkeypatch.setattr(sources, "_get", lambda url, headers=None: b"Please limit requests")
    with pytest.raises(RuntimeError, match="Please limit"):
        sources.src_gdelt("q", SINCE, UNTIL, 2000)


def test_sogou_block_is_one_gap_not_a_ceiling(monkeypatch):
    monkeypatch.setattr(sources, "_get", lambda url, headers=None: b"<html>antispider</html>")
    with pytest.raises(RuntimeError, match="captcha"):
        sources.src_sogou_wechat("q", SINCE, UNTIL, 100)

    monkeypatch.setattr(sources, "_get", lambda url, headers=None: b"<html></html>")
    assert sources.src_sogou_wechat("q", SINCE, UNTIL, 100) == ([], False)


def test_github_applies_window_and_reports_failure(monkeypatch):
    urls = []

    def fake_json(url, headers=None):
        urls.append(url)
        return {"items": [{"id": 1, "html_url": "u", "full_name": "a/b"}]}

    monkeypatch.setattr(sources, "_json", fake_json)
    recs, ceiling = sources.src_github("mcp", SINCE, UNTIL, 100)
    assert "pushed%3A2026-09-01..2026-10-01" in urls[0]
    assert "updated%3A2026-09-01..2026-10-01" in urls[1]
    assert len(recs) == 2 and ceiling is False  # a short page is the end, not a ceiling

    def rate_limited(url, headers=None):
        raise OSError("HTTP Error 403: rate limit exceeded")

    monkeypatch.setattr(sources, "_json", rate_limited)
    with pytest.raises(OSError):  # nothing collected: a gap, never a bisected window
        sources.src_github("mcp", SINCE, UNTIL, 100)


def test_telegram_honors_window_and_never_bisects(monkeypatch):
    html = (
        '<a href="https://t.me/chan/1"></a><time datetime="2026-09-10T00:00:00+00:00"></time>'
        '<div class="tgme_widget_message_text">bitcoin etf inflows rise</div>'
        '<a href="https://t.me/chan/2"></a><time datetime="2025-01-01T00:00:00+00:00"></time>'
        '<div class="tgme_widget_message_text">bitcoin etf old news</div>'
    )
    monkeypatch.setattr(sources, "_get", lambda url, headers=None: html.encode())
    recs, ceiling = sources.src_telegram("bitcoin etf", SINCE, UNTIL, 100, ["chan"])
    assert [r["url"] for r in recs] == ["https://t.me/chan/1"] and ceiling is False
    with pytest.raises(RuntimeError):
        sources.src_telegram("bitcoin etf", SINCE, UNTIL, 100, [])
