from net_sift import doctor
from net_sift.access import opencli


def test_report_keys_without_browser(monkeypatch):
    monkeypatch.setattr(opencli, "binary", lambda: None)
    monkeypatch.setattr(doctor.browsers, "detect", lambda: {})
    monkeypatch.setattr(doctor.config, "get_browser_choice", lambda home: None)
    d = doctor.report(probe=False)
    for key in ("browser", "profile_ready", "node", "keyless_sources", "web_sources", "guidance"):
        assert key in d
    assert d["profile_ready"] is False
    assert "Install OpenCLI" in d["guidance"]


def test_render_runs(monkeypatch):
    monkeypatch.setattr(opencli, "binary", lambda: None)
    monkeypatch.setattr(doctor.browsers, "detect", lambda: {})
    monkeypatch.setattr(doctor.config, "get_browser_choice", lambda home: None)
    text = doctor.render(probe=False)
    assert "net-sift doctor" in text
    assert "browser" in text


def test_probe_does_not_wait_for_a_stuck_source(monkeypatch):
    import threading

    release = threading.Event()

    def quick(q, since, until, budget):
        return [1, 2], False

    def stuck(q, since, until, budget):
        release.wait(5)
        return [], False

    def blocked(q, since, until, budget):
        import urllib.error

        raise urllib.error.HTTPError("u", 429, "Too Many Requests", None, None)

    monkeypatch.setattr(
        doctor.sources,
        "SOURCES",
        {"quick": quick, "stuck": stuck, "blocked": blocked, "telegram": quick},
    )
    monkeypatch.setattr(doctor, "PROBE_DEADLINE", 0.2)
    out = doctor._probe_keyless()
    release.set()
    assert out["quick"] == "ok (2)"
    assert out["stuck"].startswith("slow")
    assert out["blocked"] == "unreachable: HTTPError 429"
    assert out["telegram"].startswith("skipped")
    assert list(out) == ["quick", "stuck", "blocked", "telegram"]
