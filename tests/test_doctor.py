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
