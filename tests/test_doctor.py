from net_sift import doctor
from net_sift.access import opencli


def test_report_keys_without_network(monkeypatch):
    monkeypatch.setattr(opencli, "binary", lambda: None)
    d = doctor.report(probe=False)
    for key in ("opencli", "node", "walled_available", "keyless_sources", "guidance"):
        assert key in d
    assert d["walled_available"] == []
    assert "Install OpenCLI" in d["guidance"]


def test_render_runs(monkeypatch):
    monkeypatch.setattr(opencli, "binary", lambda: None)
    text = doctor.render(probe=False)
    assert "net-sift doctor" in text
    assert "opencli" in text
