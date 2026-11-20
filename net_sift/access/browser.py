"""Launch a net-sift-managed Chromium headless over CDP and guarantee teardown.

One instance per sweep. The browser is the same binary that owns the copied
profile, so it can decrypt its own cookies. It is killed and verified dead on exit.
"""

from __future__ import annotations

import base64
import contextlib
import fcntl
import functools
import json
import os
import socket
import struct
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

# CDP lives on 127.0.0.1. urllib honours HTTP(S)_PROXY, which would send these
# calls to the proxy, so they go through an opener with proxies switched off.
_local = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def local_open(url: str, method: str = "GET", timeout: float = 10):
    return _local.open(urllib.request.Request(url, method=method), timeout=timeout)


def headless_ua(raw_ua: str) -> str:
    return raw_ua.replace("HeadlessChrome", "Chrome")


@functools.cache
def real_ua(executable: str, timeout: int = 30) -> str:
    """The user agent this browser sends when headful. Headless Chrome advertises
    "HeadlessChrome", which several sites block, and a hardcoded UA drifts out of
    step with the installed version, which Reddit also blocks. So start the binary
    once on a throwaway profile, read its own UA, and drop the Headless token."""
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="netsift-ua-") as tmp:
        proc = subprocess.Popen(
            [
                executable,
                "--headless=new",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={tmp}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            if not _wait_cdp(port, timeout):
                raise RuntimeError("browser CDP did not come up while reading its user agent")
            with local_open(f"http://127.0.0.1:{port}/json/version", timeout=5) as r:
                return headless_ua(json.load(r)["User-Agent"])
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()


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
            local_open(f"http://127.0.0.1:{port}/json/version", timeout=1).close()
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
    # One browser per profile at a time, across threads and across every
    # `net-sift serve` process. A second Chromium on the same user-data-dir hands
    # off to the first and exits, so its CDP port never opens, and the pkill below
    # would then take down the sweep that is still running. Callers queue instead.
    with open(f"{profile_dir.rstrip('/')}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ua = None if headed else real_ua(executable)
        port = free_port()
        args = [
            executable,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if not headed:
            args += ["--headless=new", "--window-size=1280,900", f"--user-agent={ua}"]
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


class Page:
    """One tab driven over its CDP websocket. Stdlib only: a minimal RFC 6455 client
    (masked text frames out, plain frames in), which is all CDP needs."""

    def __init__(self, endpoint: str, url: str, timeout: float = 30):
        q = urllib.parse.quote(url, safe=":/?&=%#+,;@")
        with local_open(f"{endpoint}/json/new?{q}", method="PUT") as r:
            tab = json.load(r)
        self.endpoint, self.id, self._n = endpoint, tab["id"], 0
        ws = urllib.parse.urlsplit(tab["webSocketDebuggerUrl"])
        self.sock = socket.create_connection((ws.hostname, ws.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"GET {ws.path} HTTP/1.1\r\nHost: {ws.netloc}\r\nUpgrade: websocket\r\n"
                f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise ConnectionError("CDP websocket closed during handshake")
            head += chunk
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise ConnectionError(f"CDP websocket refused: {status!r}")

    def _read(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("CDP websocket closed")
            buf += chunk
        return buf

    def _message(self) -> dict:
        data = b""
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if b0 & 0x0F == 8:
                raise ConnectionError("CDP websocket closed by the browser")
            data += payload
            if b0 & 0x80:  # FIN: the message is complete
                return json.loads(data)

    def call(self, method: str, params: dict | None = None) -> dict:
        self._n += 1
        msg = json.dumps({"id": self._n, "method": method, "params": params or {}}).encode()
        mask = os.urandom(4)
        n = len(msg)
        head = bytes([0x81]) + (
            bytes([0x80 | n])
            if n < 126
            else bytes([0x80 | 126]) + struct.pack(">H", n)
            if n < 65536
            else bytes([0x80 | 127]) + struct.pack(">Q", n)
        )
        self.sock.sendall(head + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(msg)))
        while True:  # events arrive interleaved; skip to our reply
            reply = self._message()
            if reply.get("id") == self._n:
                if "error" in reply:
                    raise RuntimeError(f"CDP {method}: {reply['error'].get('message')}")
                return reply.get("result", {})

    def eval(self, expression: str):
        r = self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        return r.get("result", {}).get("value")

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.sock.close()
        with contextlib.suppress(OSError):
            local_open(f"{self.endpoint}/json/close/{self.id}", timeout=5).close()

    def __enter__(self) -> Page:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
