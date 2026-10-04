from net_sift.access import opencli


def test_normalize_twitter_shape():
    item = {
        "rest_id": "123",
        "full_text": "tron scaling update",
        "url": "https://x.com/a/status/123",
        "user": {"screen_name": "alice"},
        "favorite_count": 10,
        "retweet_count": 2,
        "created_at": "2026-01-02T00:00:00Z",
    }
    r = opencli.normalize(item, "twitter")
    assert r["id"] == "twitter:123"
    assert r["author"] == "alice"
    assert "tron scaling" in r["text"]
    assert r["likes"] == 10 and r["reposts"] == 2


def test_normalize_epoch_created_and_title_body():
    item = {"id": "9", "title": "Headline", "content": "body text", "taken_at": 1_700_000_000}
    r = opencli.normalize(item, "reddit")
    assert r["text"].startswith("Headline")
    assert r["created_at"].startswith("2023")


def test_normalize_skips_empty():
    assert opencli.normalize({}, "x") is None
    assert opencli.normalize("notadict", "x") is None


def test_items_envelopes():
    assert opencli._items([{"a": 1}]) == [{"a": 1}]
    assert opencli._items({"results": [{"a": 1}]}) == [{"a": 1}]
    assert opencli._items({"tweets": [{"a": 1}]}) == [{"a": 1}]
    assert opencli._items({"nope": 1}) == []


def test_walled_meta_complete():
    assert set(opencli.WALLED_META) == set(opencli.WALLED_SEARCH)


class _Proc:
    def __init__(self, returncode, stdout):
        self.returncode, self.stdout, self.stderr = returncode, stdout, ""


def test_run_uses_endpoint_and_serializes(monkeypatch):
    seen = {}

    def fake_run(cmd, capture_output, text, timeout, env=None):
        seen["endpoint"] = (env or {}).get("OPENCLI_CDP_ENDPOINT")
        return _Proc(0, '[{"title":"t","url":"u"}]')

    monkeypatch.setattr(opencli.subprocess, "run", fake_run)
    monkeypatch.setattr(opencli, "binary", lambda: "/usr/bin/opencli")
    opencli.set_endpoint("http://127.0.0.1:9999")
    try:
        out = opencli.run("google", "search", "q")
        assert seen["endpoint"] == "http://127.0.0.1:9999"
        assert out[0]["url"] == "u"
    finally:
        opencli.set_endpoint(None)


def test_sources_live_only_with_endpoint(monkeypatch):
    monkeypatch.setattr(opencli, "binary", lambda: "/usr/bin/opencli")
    opencli.set_endpoint(None)
    assert opencli.walled_sources() == {}
    assert all(not need for *_, need in opencli.OPEN_SEARCH.values()) is False  # some need browser
    public = opencli.open_sources()
    assert "wikipedia" in public and "google" not in public  # google needs the endpoint
    opencli.set_endpoint("http://127.0.0.1:1")
    try:
        assert set(opencli.walled_sources()) == set(opencli.WALLED_SEARCH)
        assert "google" in opencli.open_sources()
    finally:
        opencli.set_endpoint(None)


def test_open_sources_empty_without_binary(monkeypatch):
    monkeypatch.setattr(opencli, "binary", lambda: None)
    opencli.set_endpoint("http://127.0.0.1:1")
    try:
        assert opencli.open_sources() == {}
    finally:
        opencli.set_endpoint(None)


def test_run_empty_result_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(opencli, "binary", lambda: "/usr/bin/opencli")
    monkeypatch.setattr(
        opencli.subprocess,
        "run",
        lambda *a, **k: _Proc(1, '{"ok": false, "error": {"code": "EMPTY_RESULT"}}'),
    )
    assert opencli.run("weibo", "search", "q") == []
