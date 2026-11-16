import contextlib

from net_sift import installer


def _fake_login(tmp_path, monkeypatch, stamps, live):
    """stamps: successive auth_stamp values; live: successive _live results."""
    stamps, live = iter(stamps), iter(live)
    monkeypatch.setattr(installer.profile, "auth_stamp", lambda p, s: next(stamps))
    monkeypatch.setattr(installer, "_live", lambda s: next(live))
    # cookie presence alone must never be read as a sign-in
    monkeypatch.setattr(installer.profile, "logged_in", lambda p: {"instagram": True})

    @contextlib.contextmanager
    def fake_headed(exe, prof, headed=False, timeout=30):
        yield "http://127.0.0.1:1"

    navigated = []
    monkeypatch.setattr(installer.browser, "managed_browser", fake_headed)
    monkeypatch.setattr(installer, "_navigate", lambda endpoint, url: navigated.append(url))
    monkeypatch.setattr(installer, "_managed", lambda home: ("/bin/true", str(tmp_path / "m")))
    monkeypatch.setattr(installer.time, "sleep", lambda s: None)
    return navigated


def test_login_sites_waits_for_fresh_cookie(tmp_path, monkeypatch):
    # no cookie, then one appears and search works
    _fake_login(tmp_path, monkeypatch, [None, None, 5], [None])
    res = installer.login_sites(tmp_path, ["twitter"], installer._UI(assume_yes=True))
    assert res["twitter"] is True


def test_login_sites_stale_cookie_is_not_success(tmp_path, monkeypatch):
    # expired cookie present, search fails, user never signs in again
    navigated = _fake_login(tmp_path, monkeypatch, [7] * 4, ["blocked"])
    res = installer.login_sites(tmp_path, ["instagram"], installer._UI(assume_yes=True), poll=3)
    assert res["instagram"] is False
    assert navigated  # the login page was actually opened


def test_login_sites_skips_working_session(tmp_path, monkeypatch):
    navigated = _fake_login(tmp_path, monkeypatch, [7], [None])
    res = installer.login_sites(tmp_path, ["twitter"], installer._UI(assume_yes=True))
    assert res["twitter"] is True and not navigated


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
    assert installer._classify("code: COMMAND_EXEC Instagram search failed: HTTP 404") == "error"


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
