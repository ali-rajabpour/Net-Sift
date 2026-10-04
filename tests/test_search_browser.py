import contextlib

from net_sift import search


def test_sweep_opens_and_sets_endpoint(monkeypatch, tmp_path):
    events = []

    @contextlib.contextmanager
    def fake_managed(exe, prof, headed=False, timeout=30):
        events.append(("open", prof))
        try:
            yield "http://127.0.0.1:1234"
        finally:
            events.append(("close", prof))

    monkeypatch.setattr(search, "_managed_profile", lambda: ("/bin/true", str(tmp_path / "p")))
    monkeypatch.setattr(search.browser, "managed_browser", fake_managed)
    monkeypatch.setattr(search, "_needs_browser", lambda names, smap: True)
    captured = {}

    def fake_run(*a, **k):
        captured["endpoint"] = search.opencli.current_endpoint()
        return [], ["x[0] 0 records"]

    monkeypatch.setattr(search.core, "run", fake_run)
    monkeypatch.setattr(
        search.sessions,
        "save",
        lambda *a, **k: {"id": "s", "count": 0, "sources": {}, "corpus": "c"},
    )
    search.deep_search("q", platforms=["google"])
    assert ("open", str(tmp_path / "p")) in events
    assert ("close", str(tmp_path / "p")) in events
    assert captured["endpoint"] == "http://127.0.0.1:1234"  # set during the sweep
    assert search.opencli.current_endpoint() is None  # cleared after


def test_browser_gap_when_no_profile(monkeypatch, tmp_path):
    monkeypatch.setattr(search, "_managed_profile", lambda: None)
    monkeypatch.setattr(search.core, "run", lambda *a, **k: ([], []))
    monkeypatch.setattr(
        search.sessions,
        "save",
        lambda *a, **k: {"id": "s", "count": 0, "sources": {}, "corpus": "c"},
    )
    out = search.deep_search("q", platforms=["twitter"])
    assert any("no managed profile" in g for g in out["gaps"])


def test_browser_choice_roundtrip(tmp_path):
    from net_sift import config

    assert config.get_browser_choice(tmp_path) is None
    config.set_browser_choice(tmp_path, "comet")
    assert config.get_browser_choice(tmp_path) == "comet"
