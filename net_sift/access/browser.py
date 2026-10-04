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

# A desktop Chrome user agent with no "Headless" token; headless Chrome otherwise
# advertises "HeadlessChrome", which several sites block.
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
    """Yield a CDP base URL for a managed browser; always tear it down on exit."""
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
