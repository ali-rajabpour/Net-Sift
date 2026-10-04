# Headless Browser Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let net-sift search walled and open-web sources with the browser closed, by driving a self-managed headless Chromium over CDP against a copy of the user's logged-in profile, and never leaving a browser process alive.

**Architecture:** Three new modules under `net_sift/access/` (browser discovery, profile copy + session detection, browser lifecycle). The OpenCLI access layer is rewritten to drive a net-sift-launched browser via `OPENCLI_CDP_ENDPOINT` instead of the extension bridge. A sweep opens one headless browser, runs browser-backed sources serialized and keyless sources in parallel, then kills and verifies the browser dead.

**Tech Stack:** Python 3.10+ stdlib only (subprocess, sqlite3, shutil, urllib, threading), OpenCLI binary as the adapter + CDP driver.

**Spec:** `docs/specs/2026-10-04-headless-browser-access-design.md`

## Global Constraints

- Python >= 3.10, stdlib only; no new runtime dependency (deps stay `mcp>=2.2.0`, `defusedxml>=0.7.1`).
- No AI attribution anywhere; no em dashes in any file.
- Author commits as the repo user; commit messages concise and human.
- macOS first. Windows and Linux are out of scope this release (TODO only).
- Managed profile directory created `0700`; CDP bound to `127.0.0.1` on a random port; browser killed and verified dead after every sweep.
- No fallback: the OpenCLI extension/daemon path is removed, not kept beside the new one.
- ruff check + ruff format + pytest must pass.

## Review Focus

- Browser process must be killed even when a source raises mid-sweep: teardown in a `finally`, verified by pgrep on the user-data-dir. (Task 3)
- A second concurrent OpenCLI call against one endpoint breaks the page; browser sources must serialize. (Task 4)
- `copy_profile` run while the source browser is live must still produce a usable copy, and must never write to the source. (Task 2)
- `logged_in` must read cookie names only and must not crash on a locked or absent Cookies DB. (Task 2)
- Headless user agent must not contain "HeadlessChrome" or Google blocks the sweep. (Task 3)

---

## Task 1: Browser discovery (`access/browsers.py`)

**Files:**
- Create: `net_sift/access/browsers.py`
- Test: `tests/test_browsers.py`

**Interfaces:**
- Produces: `MAC_BROWSERS: dict[str, tuple[str, str]]` (id -> (executable path, source profile dir)); `detect() -> dict[str, dict]` returning `{id: {"id", "name", "executable", "source_profile"}}` for browsers whose executable and `Default` profile both exist.

- [ ] **Step 1: Write the failing test**

```python
from net_sift.access import browsers

def test_detect_only_present(tmp_path, monkeypatch):
    exe = tmp_path / "Chrome"; exe.write_text("")
    prof = tmp_path / "prof"; (prof / "Default").mkdir(parents=True)
    monkeypatch.setattr(browsers, "MAC_BROWSERS", {"chrome": ("Google Chrome", str(exe), str(prof))})
    d = browsers.detect()
    assert set(d) == {"chrome"}
    assert d["chrome"]["executable"] == str(exe)
    assert d["chrome"]["source_profile"] == str(prof)

def test_detect_skips_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(browsers, "MAC_BROWSERS", {"ghost": ("Ghost", str(tmp_path / "nope"), str(tmp_path / "nope"))})
    assert browsers.detect() == {}
```

- [ ] **Step 2: Run to verify fail** — `pytest tests/test_browsers.py -v` -> FAIL (module missing).

- [ ] **Step 3: Implement**

```python
"""Discover installed Chromium browsers on macOS: executable and source profile dir."""

from __future__ import annotations

import os
from pathlib import Path

_SUPPORT = Path.home() / "Library" / "Application Support"
_APPS = Path("/Applications")

# id -> (display name, executable path, source user-data-dir)
MAC_BROWSERS: dict[str, tuple[str, str, str]] = {
    "chrome": ("Google Chrome", str(_APPS / "Google Chrome.app/Contents/MacOS/Google Chrome"), str(_SUPPORT / "Google/Chrome")),
    "comet": ("Comet", str(_APPS / "Comet.app/Contents/MacOS/Comet"), str(_SUPPORT / "Comet")),
    "brave": ("Brave", str(_APPS / "Brave Browser.app/Contents/MacOS/Brave Browser"), str(_SUPPORT / "BraveSoftware/Brave-Browser")),
    "edge": ("Microsoft Edge", str(_APPS / "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"), str(_SUPPORT / "Microsoft Edge")),
    "arc": ("Arc", str(_APPS / "Arc.app/Contents/MacOS/Arc"), str(_SUPPORT / "Arc/User Data")),
    "vivaldi": ("Vivaldi", str(_APPS / "Vivaldi.app/Contents/MacOS/Vivaldi"), str(_SUPPORT / "Vivaldi")),
    "chromium": ("Chromium", str(_APPS / "Chromium.app/Contents/MacOS/Chromium"), str(_SUPPORT / "Chromium")),
}


def detect() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for bid, (name, exe, prof) in MAC_BROWSERS.items():
        if os.path.exists(exe) and os.path.isdir(os.path.join(prof, "Default")):
            out[bid] = {"id": bid, "name": name, "executable": exe, "source_profile": prof}
    return out
```

- [ ] **Step 4: Run** — `pytest tests/test_browsers.py -v` -> PASS.
- [ ] **Step 5: Commit** — `git add net_sift/access/browsers.py tests/test_browsers.py && git commit -m "Add Chromium browser discovery for macOS"`

---

## Task 2: Profile copy + session detection (`access/profile.py`)

**Files:**
- Create: `net_sift/access/profile.py`
- Test: `tests/test_profile.py`

**Interfaces:**
- Consumes: `browsers.detect()` entries.
- Produces:
  - `managed_dir(home, browser_id) -> Path` (`<home>/profiles/<id>`).
  - `copy_profile(source_profile, dest) -> Path` (copies `Local State` and selected `Default` items; `dest` created `0700`; never writes source).
  - `AUTH_COOKIES: dict[str, tuple[str, ...]]` (site id -> host-suffix, names).
  - `logged_in(profile_dir) -> dict[str, bool]` (site id -> logged in; reads cookie names only; tolerant of missing/locked DB).

- [ ] **Step 1: Write the failing test**

```python
import sqlite3, stat
from pathlib import Path
from net_sift.access import profile

def _cookies_db(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("create table cookies (host_key text, name text, encrypted_value blob)")
    c.executemany("insert into cookies values (?,?,?)", rows)
    c.commit(); c.close()

def test_copy_profile_0700_and_readonly_source(tmp_path):
    src = tmp_path / "src"; (src / "Default").mkdir(parents=True)
    (src / "Local State").write_text("{}")
    _cookies_db(src / "Default" / "Cookies", [(".x.com", "auth_token", b"enc")])
    dest = tmp_path / "managed"
    out = profile.copy_profile(str(src), str(dest))
    assert (Path(out) / "Local State").exists()
    assert (Path(out) / "Default" / "Cookies").exists()
    assert stat.S_IMODE(Path(out).stat().st_mode) == 0o700
    assert (src / "Local State").read_text() == "{}"  # untouched

def test_logged_in_reads_names_only(tmp_path):
    prof = tmp_path / "p"
    _cookies_db(prof / "Default" / "Cookies", [(".x.com", "auth_token", b""), (".reddit.com", "reddit_session", b"")])
    st = profile.logged_in(str(prof))
    assert st["twitter"] is True and st["reddit"] is True
    assert st["zhihu"] is False

def test_logged_in_missing_db(tmp_path):
    assert profile.logged_in(str(tmp_path / "none")) == {k: False for k in profile.AUTH_COOKIES}
```

- [ ] **Step 2: Run to verify fail** — `pytest tests/test_profile.py -v` -> FAIL.

- [ ] **Step 3: Implement**

```python
"""Copy a browser's profile into net-sift's managed area and detect logged-in sites.

Cookie VALUES are encrypted with a per-browser key, so a copy is only usable when
driven by the same browser binary. Cookie NAMES are plaintext, so logged-in sites
can be detected without decrypting anything. The source profile is only read.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

# site id -> (host suffix, auth cookie names any of which means logged in)
AUTH_COOKIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "twitter": ("x.com", ("auth_token", "ct0")),
    "reddit": ("reddit.com", ("reddit_session",)),
    "instagram": ("instagram.com", ("sessionid",)),
    "facebook": ("facebook.com", ("c_user", "xs")),
    "bilibili": ("bilibili.com", ("SESSDATA",)),
    "xiaohongshu": ("xiaohongshu.com", ("web_session",)),
    "zhihu": ("zhihu.com", ("z_c0",)),
    "weibo": ("weibo.com", ("SUB",)),
    "google": ("google.com", ("SID", "__Secure-1PSID")),
    "youtube": ("youtube.com", ("SID", "__Secure-1PSID")),
}

# Items under Default worth copying: cookies live in Network/Cookies on current
# Chromium, Cookies on older; both are tried.
_DEFAULT_ITEMS = ("Network/Cookies", "Cookies", "Preferences", "Local Storage", "Login Data")


def managed_dir(home: Path, browser_id: str) -> Path:
    return Path(home) / "profiles" / browser_id


def copy_profile(source_profile: str, dest: str) -> str:
    src = Path(source_profile)
    dst = Path(dest)
    shutil.rmtree(dst, ignore_errors=True)
    (dst / "Default").mkdir(parents=True)
    os.chmod(dst, 0o700)
    ls = src / "Local State"
    if ls.exists():
        shutil.copy2(ls, dst / "Local State")
    for item in _DEFAULT_ITEMS:
        s = src / "Default" / item
        if s.exists():
            d = dst / "Default" / item
            d.parent.mkdir(parents=True, exist_ok=True)
            if s.is_dir():
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
    return str(dst)


def _cookie_db(profile_dir: Path) -> Path | None:
    for rel in ("Default/Network/Cookies", "Default/Cookies"):
        p = profile_dir / rel
        if p.exists():
            return p
    return None


def logged_in(profile_dir: str) -> dict[str, bool]:
    out = {site: False for site in AUTH_COOKIES}
    db = _cookie_db(Path(profile_dir))
    if not db:
        return out
    # Copy first: the live DB may be WAL-locked by a running browser.
    tmp = Path(tempfile.gettempdir()) / f"netsift-ck-{os.getpid()}.db"
    try:
        shutil.copy2(db, tmp)
        con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        names = {(h, n) for h, n in con.execute("select host_key, name from cookies")}
        con.close()
    except (OSError, sqlite3.Error):
        return out
    finally:
        tmp.unlink(missing_ok=True)
    for site, (host, cookie_names) in AUTH_COOKIES.items():
        out[site] = any(
            h.endswith(host) and n in cookie_names for h, n in names
        )
    return out
```

- [ ] **Step 4: Run** — `pytest tests/test_profile.py -v` -> PASS.
- [ ] **Step 5: Commit** — `git add net_sift/access/profile.py tests/test_profile.py && git commit -m "Add profile copy and logged-in detection by cookie name"`

---

## Task 3: Browser lifecycle (`access/browser.py`)

**Files:**
- Create: `net_sift/access/browser.py`
- Test: `tests/test_browser.py`

**Interfaces:**
- Consumes: `browsers.detect()`, `profile.managed_dir`.
- Produces:
  - `headless_ua(raw_ua: str) -> str` (replaces `HeadlessChrome` with `Chrome`).
  - `free_port() -> int`.
  - `managed_browser(executable, profile_dir, headed=False, timeout=30) -> ContextManager[str]` yielding the CDP base URL, guaranteeing teardown.

- [ ] **Step 1: Write the failing test**

```python
from net_sift.access import browser

def test_headless_ua_strips_token():
    raw = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/153.0.0.0 Safari/537.36"
    assert "HeadlessChrome" not in browser.headless_ua(raw)
    assert "Chrome/153" in browser.headless_ua(raw)

def test_free_port_is_int():
    p = browser.free_port()
    assert isinstance(p, int) and 1024 < p < 65536

def test_managed_browser_tears_down(monkeypatch, tmp_path):
    calls = {"terminated": False, "waited": False, "alive_checks": 0}

    class FakeProc:
        pid = 4321
        def terminate(self): calls["terminated"] = True
        def wait(self, timeout=None): calls["waited"] = True; return 0
        def kill(self): pass
        def poll(self): return 0

    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr(browser, "_wait_cdp", lambda port, timeout: True)
    monkeypatch.setattr(browser, "_running_for", lambda d: calls.__setitem__("alive_checks", calls["alive_checks"] + 1) or 0)
    with browser.managed_browser("/bin/true", str(tmp_path / "p")) as endpoint:
        assert endpoint.startswith("http://127.0.0.1:")
    assert calls["terminated"] and calls["waited"] and calls["alive_checks"] >= 1

def test_managed_browser_tears_down_on_error(monkeypatch, tmp_path):
    class FakeProc:
        pid = 1
        def terminate(self): self.t = True
        def wait(self, timeout=None): return 0
        def kill(self): pass
        def poll(self): return 0
    fp = FakeProc()
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *a, **k: fp)
    monkeypatch.setattr(browser, "_wait_cdp", lambda port, timeout: True)
    monkeypatch.setattr(browser, "_running_for", lambda d: 0)
    import pytest
    with pytest.raises(RuntimeError):
        with browser.managed_browser("/bin/true", str(tmp_path / "p")):
            raise RuntimeError("boom")
    assert getattr(fp, "t", False)  # terminated despite the error
```

- [ ] **Step 2: Run to verify fail** — `pytest tests/test_browser.py -v` -> FAIL.

- [ ] **Step 3: Implement**

```python
"""Launch a net-sift-managed Chromium headless over CDP and guarantee teardown.

One instance per sweep. The browser is the same binary that owns the copied
profile, so it can decrypt its own cookies. It is killed and verified dead on exit.
"""

from __future__ import annotations

import contextlib
import socket
import subprocess
import time
import urllib.request

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"
)


def headless_ua(raw_ua: str) -> str:
    return raw_ua.replace("HeadlessChrome", "Chrome")


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_cdp(port: int, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def _running_for(user_data_dir: str) -> int:
    p = subprocess.run(["pgrep", "-f", user_data_dir], capture_output=True, text=True)
    return len([x for x in p.stdout.split() if x])


@contextlib.contextmanager
def managed_browser(executable: str, profile_dir: str, headed: bool = False, timeout: int = 30):
    port = free_port()
    args = [
        executable,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if not headed:
        args += ["--headless=new", "--window-size=1280,900", f"--user-agent={_UA}"]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not _wait_cdp(port, timeout):
            raise RuntimeError(f"browser CDP did not come up on port {port}")
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
        time.sleep(1.0)
        if _running_for(profile_dir):
            subprocess.run(["pkill", "-f", profile_dir])
```

- [ ] **Step 4: Run** — `pytest tests/test_browser.py -v` -> PASS.
- [ ] **Step 5: Commit** — `git add net_sift/access/browser.py tests/test_browser.py && git commit -m "Add managed headless browser lifecycle with guaranteed teardown"`

---

## Task 4: Rewrite OpenCLI access to drive the managed endpoint

**Files:**
- Modify: `net_sift/access/opencli.py`
- Test: `tests/test_opencli.py` (replace extension-era tests), `tests/test_web_sources.py` (serialization)

**Interfaces:**
- Consumes: nothing new at import; `run()` reads a module-global endpoint.
- Produces:
  - `set_endpoint(url: str | None)` and `current_endpoint() -> str | None`.
  - `run(site, command, *args, ...)` sets `OPENCLI_CDP_ENDPOINT` from the endpoint and serializes via a module lock.
  - `walled_sources(connected=None)` / `open_sources(connected=None)` keyed off `current_endpoint()` being set.
  - Remove: `doctor_text`, `_parse_connected`, `available`, `available_cached`, `discover`, `_parse_list_json`, `_parse_list_text`.

- [ ] **Step 1: Write the failing test**

```python
from net_sift.access import opencli

def test_run_uses_endpoint_and_serializes(monkeypatch):
    seen = {}
    class P:
        returncode = 0
        stdout = '[{"title":"t","url":"u"}]'
        stderr = ""
    def fake_run(cmd, capture_output, text, timeout, env=None):
        seen["endpoint"] = env.get("OPENCLI_CDP_ENDPOINT")
        return P()
    monkeypatch.setattr(opencli.subprocess, "run", fake_run)
    monkeypatch.setattr(opencli.shutil, "which", lambda n: "/usr/bin/opencli")
    opencli.set_endpoint("http://127.0.0.1:9999")
    out = opencli.run("google", "search", "q")
    assert seen["endpoint"] == "http://127.0.0.1:9999"
    assert out[0]["url"] == "u"
    opencli.set_endpoint(None)

def test_sources_live_only_with_endpoint(monkeypatch):
    monkeypatch.setattr(opencli, "binary", lambda: "/usr/bin/opencli")
    opencli.set_endpoint(None)
    assert opencli.walled_sources() == {}
    opencli.set_endpoint("http://127.0.0.1:1")
    assert set(opencli.walled_sources()) == set(opencli.WALLED_SEARCH)
    opencli.set_endpoint(None)
```

- [ ] **Step 2: Run to verify fail** — `pytest tests/test_opencli.py -v` -> FAIL.

- [ ] **Step 3: Implement.** In `opencli.py`:
  - Add module state and lock:
    ```python
    import threading
    _ENDPOINT: str | None = None
    _run_lock = threading.Lock()

    def set_endpoint(url: str | None) -> None:
        global _ENDPOINT
        _ENDPOINT = url

    def current_endpoint() -> str | None:
        return _ENDPOINT
    ```
  - In `run()`, build `env = {**os.environ}`, set `env["OPENCLI_CDP_ENDPOINT"] = _ENDPOINT` when set, pass `env=env` to `subprocess.run`, and wrap the call body in `with _run_lock:` so browser sources never overlap.
  - Change `walled_sources` / `open_sources` to treat `connected` as `current_endpoint() is not None` when `connected is None`.
  - Delete `doctor_text`, `_parse_connected`, `available`, `available_cached`, `discover`, `_parse_list_json`, `_parse_list_text`, and the `OpenCLIUnavailable`-via-extension messaging about "no browser session". Keep `binary()`, `OpenCLIUnavailable`, normalization, `make_source`, `OPEN_SEARCH`, `WALLED_SEARCH`, `WALLED_META`, `WALLED_SITES`, `probe_detail`/`probe_login` (still useful for `net-sift login`).
  - Remove extension-era tests in `tests/test_opencli.py` (`test_available_*`, `test_parse_connected`, `test_parse_list_*`, `test_walled_sources` that asserted on connectivity) and keep normalization/`make_source` tests, updating `walled_sources` tests to the endpoint form above.

- [ ] **Step 4: Run** — `pytest tests/test_opencli.py tests/test_web_sources.py -v` -> PASS.
- [ ] **Step 5: Commit** — `git add net_sift/access/opencli.py tests/test_opencli.py && git commit -m "Drive OpenCLI over a managed CDP endpoint, drop the extension bridge"`

---

## Task 5: Wire the managed browser into a sweep (`search.py`)

**Files:**
- Modify: `net_sift/search.py`
- Modify: `net_sift/config.py` (saved browser choice helpers)
- Test: `tests/test_search_browser.py`

**Interfaces:**
- Consumes: `browsers.detect`, `profile.managed_dir`, `browser.managed_browser`, `opencli.set_endpoint`, `config.get_browser_choice`.
- Produces: `deep_search(...)` opens one managed browser for the whole sweep when any browser-backed source is selected and a managed profile exists; sets/clears the endpoint around the sweep; records a gap when no managed profile is set but browser sources were requested.
- `config.get_browser_choice(home) -> str | None`, `config.set_browser_choice(home, id)`.

- [ ] **Step 1: Write the failing test**

```python
from net_sift import search

def test_sweep_opens_and_sets_endpoint(monkeypatch, tmp_path):
    events = []
    import contextlib
    @contextlib.contextmanager
    def fake_managed(exe, prof, headed=False, timeout=30):
        events.append(("open", prof)); search.opencli.set_endpoint("http://127.0.0.1:1234")
        try: yield "http://127.0.0.1:1234"
        finally: events.append(("close", prof)); search.opencli.set_endpoint(None)
    monkeypatch.setattr(search, "_managed_profile", lambda: ("/bin/true", str(tmp_path / "p")))
    monkeypatch.setattr(search.browser, "managed_browser", fake_managed)
    monkeypatch.setattr(search, "_needs_browser", lambda names, smap: True)
    monkeypatch.setattr(search.core, "run", lambda *a, **k: ([], ["x[0] 0 records"]))
    monkeypatch.setattr(search.sessions, "save", lambda *a, **k: {"id": "s", "count": 0, "sources": {}, "corpus": "c"})
    search.deep_search("q", platforms=["google"])
    assert ("open", str(tmp_path / "p")) in events and ("close", str(tmp_path / "p")) in events
    assert search.opencli.current_endpoint() is None  # cleared after
```

- [ ] **Step 2: Run to verify fail** — `pytest tests/test_search_browser.py -v` -> FAIL.

- [ ] **Step 3: Implement**
  - `config.get_browser_choice`/`set_browser_choice`: store `{"browser": id}` in `<home>/browser.json`.
  - `search._managed_profile() -> tuple[str, str] | None`: resolve chosen browser from `NET_SIFT_BROWSER` or `config.get_browser_choice`, map to executable via `browsers.detect()`, and return `(executable, str(profile.managed_dir(config.HOME, id)))` only if that managed dir exists.
  - `search._needs_browser(names, source_map)`: any selected name is in `opencli.WALLED_SITES` or `opencli.OPEN_SEARCH`.
  - In `deep_search`: if `_needs_browser` and `_managed_profile()` returns a path, wrap the `core.run` call in `with browser.managed_browser(exe, prof): opencli.set_endpoint(...)`; the context already sets the endpoint. If browser sources were requested but no managed profile exists, append a gap: `"browser[0] FAILED: no managed profile; run net-sift install"`. Always clear the endpoint after.
  - `all_sources()` keeps building browser-backed sources; they no-op cleanly when the endpoint is unset (they will only be run inside the context).

- [ ] **Step 4: Run** — `pytest tests/test_search_browser.py -v` -> PASS.
- [ ] **Step 5: Commit** — `git add net_sift/search.py net_sift/config.py tests/test_search_browser.py && git commit -m "Open one managed headless browser per sweep"`

---

## Task 6: `net-sift login` and wizard rewrite

**Files:**
- Modify: `net_sift/installer.py`, `net_sift/cli.py`
- Modify: `net_sift/doctor.py`, `net_sift/status.py`
- Test: `tests/test_login.py`, update `tests/test_doctor.py`, `tests/test_config_status.py`, `tests/test_cli_install.py`, `tests/test_installer.py`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces:
  - `installer.login_sites(home, sites, ui) -> dict[str, bool]`: open the managed profile headed once, for each site navigate (new tab if already open) to its login URL, poll `profile.logged_in` for that site until present or the user skips, return per-site result. (Headed, interactive; unit-tested with a fake browser + fake UI.)
  - `installer.setup_browser(home, ui)`: detect browsers, show per-site login status from each source profile, let the user pick, copy the profile into the managed dir, re-detect, offer `login_sites` for missing walled sites.
  - `cli`: add `login` subcommand calling `installer.login_sites`.
  - `doctor.report`: replace `opencli`/`walled_available` extension fields with `browser` (chosen id), `managed_profile` (path + exists), and `sites` (per-site logged-in from the managed profile). `status.snapshot`/`line`: "profile ready / N sites" instead of "browser connected".

- [ ] **Step 1: Write the failing test**

```python
from net_sift import installer

LOGIN_URLS = installer.LOGIN_URLS

def test_login_sites_polls_until_present(tmp_path, monkeypatch):
    seq = iter([{"twitter": False}, {"twitter": True}])
    monkeypatch.setattr(installer.profile, "logged_in", lambda p: next(seq))
    import contextlib
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
```

- [ ] **Step 2: Run to verify fail** — `pytest tests/test_login.py -v` -> FAIL.

- [ ] **Step 3: Implement**
  - Add `LOGIN_URLS = {"twitter": "https://x.com/login", "reddit": "https://www.reddit.com/login", "instagram": "https://www.instagram.com/accounts/login/", "facebook": "https://www.facebook.com/login", "bilibili": "https://passport.bilibili.com/login", "xiaohongshu": "https://www.xiaohongshu.com", "zhihu": "https://www.zhihu.com/signin", "weibo": "https://weibo.com/login.php"}`.
  - `_navigate(endpoint, url)`: open a tab via the CDP HTTP endpoint `PUT /json/new?<url>` (urllib), so a second site reuses the same browser as a new tab.
  - `login_sites`: open `managed_browser(..., headed=True)` once; for each site call `_navigate`, then poll `profile.logged_in` up to N times with a sleep, pausing for the user (`ui.pause`) between sites; mark skipped on user skip.
  - `setup_browser`: detect -> show `profile.logged_in(source_profile)` per browser -> `ui.choose` -> `copy_profile` into `managed_dir` -> `config.set_browser_choice` -> re-detect from managed -> `login_sites` for walled sites still false (confirm first).
  - Replace the old `_choose_browser`/Node/OpenCLI-extension steps that referenced the extension connect flow; keep Node + OpenCLI binary install steps (still needed).
  - `cli`: `login` subcommand, args: optional `sites` (comma list); default = all not-logged-in walled sites.
  - `doctor`/`status`: new fields as above; update their tests.

- [ ] **Step 4: Run** — `pytest -v` (all) -> PASS.
- [ ] **Step 5: Commit** — `git add -A net_sift tests && git commit -m "Add net-sift login and rewrite wizard for managed profiles"`

---

## Task 7: Docs, changelog, version bump, cleanup

**Files:**
- Modify: `README.md`, `net_sift/guides/sources.md`, `net_sift/guides/setup-opencli.md`, `CHANGELOG.md`, `pyproject.toml`, `docs/architecture.md`
- Create: `scripts/browser_matrix.py` (manual integration check, not CI)

**Interfaces:** none (docs + metadata).

- [ ] **Step 1: Edit docs.** README: remove "net-sift never reads or copies browser cookies"; describe the opt-in profile copy, headless search, `net-sift login`, macOS-only note. sources.md: note walled + browser-open sources need a managed profile, not a live browser. setup-opencli.md: drop the extension steps, keep the binary install. architecture.md: update the access description.
- [ ] **Step 2: Version + changelog.** `pyproject.toml` version -> `1.0.0`. CHANGELOG `[1.0.0]` with Added (managed headless browser, profile copy, `net-sift login`, session detection), Changed (searches run with the browser closed; wizard copies a profile), Removed (OpenCLI extension bridge; `fetch` note already done).
- [ ] **Step 3: Manual matrix script.** Write `scripts/browser_matrix.py` (the spike matrix) that, given a managed profile, launches headless and runs each browser source once, printing OK/fail and asserting zero leftover processes. Header comment: needs a real logged-in profile, run by hand, not in CI.
- [ ] **Step 4: Run** `ruff check net_sift tests && ruff format --check net_sift tests && pytest` -> all pass.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "Document managed-profile access, bump to 1.0.0"`

---

## Deferred (needs Ali at the machine; not in this plan's automated run)

- One-time `net-sift install` / `net-sift login` headed runs (interactive).
- `scripts/browser_matrix.py` against a real logged-in profile.
- Windows and Linux support.
- Live verification of Brave API / GDELT / Marginalia; OpenCLI brave/duckduckgo/36kr firewall retest; weibo/jike logged-in checks; stocktwits/github partial-failure handling.
- Release (tag v1.0.0, push, watch CI) after Ali verifies the headed steps.
