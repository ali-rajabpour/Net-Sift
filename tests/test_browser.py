import pytest

from net_sift.access import browser


def test_headless_ua_strips_token():
    raw = (
        "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 (KHTML, like Gecko) "
        "HeadlessChrome/153.0.0.0 Safari/537.36"
    )
    assert "HeadlessChrome" not in browser.headless_ua(raw)
    assert "Chrome/153" in browser.headless_ua(raw)


def test_free_port_is_int():
    p = browser.free_port()
    assert isinstance(p, int) and 1024 < p < 65536


def test_managed_browser_tears_down(monkeypatch, tmp_path):
    calls = {"terminated": False, "waited": False, "alive_checks": 0}

    class FakeProc:
        pid = 4321

        def terminate(self):
            calls["terminated"] = True

        def wait(self, timeout=None):
            calls["waited"] = True
            return 0

        def kill(self):
            pass

        def poll(self):
            return 0

    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr(browser, "_wait_cdp", lambda port, timeout: True)
    monkeypatch.setattr(
        browser,
        "_running_for",
        lambda d: calls.__setitem__("alive_checks", calls["alive_checks"] + 1) or 0,
    )
    with browser.managed_browser("/bin/true", str(tmp_path / "p")) as endpoint:
        assert endpoint.startswith("http://127.0.0.1:")
    assert calls["terminated"] and calls["waited"] and calls["alive_checks"] >= 1


def test_managed_browser_tears_down_on_error(monkeypatch, tmp_path):
    class FakeProc:
        pid = 1
        t = False

        def terminate(self):
            self.t = True

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

        def poll(self):
            return 0

    fp = FakeProc()
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: fp)
    monkeypatch.setattr(browser, "_wait_cdp", lambda port, timeout: True)
    monkeypatch.setattr(browser, "_running_for", lambda d: 0)
    with pytest.raises(RuntimeError):
        with browser.managed_browser("/bin/true", str(tmp_path / "p")):
            raise RuntimeError("boom")
    assert fp.t  # terminated despite the error
