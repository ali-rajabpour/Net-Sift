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


def test_classify():
    assert installer._classify("code: AUTH_REQUIRED message: Not logged in") == "login"
    assert installer._classify("code: TIMEOUT xiaohongshu timed out") == "timeout"
    assert installer._classify("COMMAND_EXEC Pre-navigation to ... failed") == "blocked"
    assert installer._classify("Navigation rejected.") == "blocked"
    assert (
        installer._classify("code: NOT_FOUND No search results found, check for CAPTCHA")
        == "blocked"
    )
    assert installer._classify("non-JSON output") == "error"


def test_verify_sources_reports_and_offers_login(tmp_path, monkeypatch):
    import contextlib

    monkeypatch.setattr(installer, "_managed", lambda home: ("/bin/true", str(tmp_path / "m")))

    @contextlib.contextmanager
    def fake_browser(exe, prof, headed=False, timeout=30):
        yield "http://127.0.0.1:1"

    monkeypatch.setattr(installer.browser, "managed_browser", fake_browser)

    def fake_make_source(site, cmd, name=None, cap=100):
        label = name or site

        def src(q, s, u, b):
            if label == "twitter":
                raise installer.opencli.OpenCLIUnavailable("exit 77: code: AUTH_REQUIRED")
            if label == "google":
                return [{"source": "google"}], False
            return [], False

        return src

    monkeypatch.setattr(installer.opencli, "make_source", fake_make_source)
    offered = []
    monkeypatch.setattr(
        installer, "login_sites", lambda home, sites, ui: offered.extend(sites) or {}
    )

    # a UI that says yes only to logging in twitter
    class UI(installer._UI):
        def confirm(self, msg, default=True):
            return "twitter" in msg

    ui = UI(assume_yes=False)
    res = installer.verify_sources(tmp_path, ui)
    assert res["twitter"] == ("fail", "login")
    assert res["google"][0] == "ok"
    assert offered == ["twitter"]  # offered a login for the auth-failed site
