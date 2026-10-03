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


def test_parse_list_json():
    txt = '[{"site":"twitter","command":"search"},{"site":"reddit","command":"search"}]'
    cat = opencli._parse_list_json(txt)
    assert cat["twitter"] == ["search"] and cat["reddit"] == ["search"]


def test_parse_list_text():
    txt = "twitter search  - search tweets\nreddit search  - search posts\n# comment\n"
    cat = opencli._parse_list_text(txt)
    assert "search" in cat["twitter"] and "search" in cat["reddit"]


def test_available_false_without_binary(monkeypatch):
    monkeypatch.setattr(opencli, "binary", lambda: None)
    assert opencli.available() is False
    assert opencli.walled_sources() == {}


def test_parse_connected():
    doc = "[OK] Extension: connected (v1.0.24)\n[OK] Connectivity: connected in 4.6s"
    assert opencli._parse_connected(doc) is True
    assert opencli._parse_connected("Extension: disconnected") is False
    assert opencli._parse_connected(None) is False


def test_available_from_doctor(monkeypatch):
    monkeypatch.setattr(
        opencli, "doctor_text", lambda timeout=30: "[OK] Connectivity: connected in 1s"
    )
    assert opencli.available() is True
    monkeypatch.setattr(opencli, "doctor_text", lambda timeout=30: "[!] Extension: reconnecting")
    assert opencli.available() is False


def test_available_cached(tmp_path, monkeypatch):
    from net_sift import config

    monkeypatch.setattr(config, "HOME", tmp_path)
    calls = []

    def fake_doctor(timeout=30):
        calls.append(1)
        return "Connectivity: connected"

    monkeypatch.setattr(opencli, "doctor_text", fake_doctor)
    assert opencli.available_cached() is True
    assert opencli.available_cached() is True  # second read hits cache
    assert len(calls) == 1
