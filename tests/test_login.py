import contextlib

from net_sift import installer


def test_login_sites_polls_until_present(tmp_path, monkeypatch):
    seq = iter([{"twitter": False}, {"twitter": True}])
    monkeypatch.setattr(installer.profile, "logged_in", lambda p: next(seq))

    @contextlib.contextmanager
    def fake_headed(exe, prof, headed=False, timeout=30):
        yield "http://127.0.0.1:1"

    monkeypatch.setattr(installer.browser, "managed_browser", fake_headed)
    monkeypatch.setattr(installer, "_navigate", lambda endpoint, url: None)
    monkeypatch.setattr(installer, "_managed", lambda home: ("/bin/true", str(tmp_path / "m")))
    monkeypatch.setattr(installer.time, "sleep", lambda s: None)
    ui = installer._UI(assume_yes=True)
    res = installer.login_sites(tmp_path, ["twitter"], ui)
    assert res["twitter"] is True


def test_login_sites_no_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "_managed", lambda home: None)
    ui = installer._UI(assume_yes=True)
    assert installer.login_sites(tmp_path, ["reddit"], ui) == {"reddit": False}
