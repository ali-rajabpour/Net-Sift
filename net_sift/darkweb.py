"""Read-only discussion search across Tor onion forums. INFORMATION ONLY.

Discovers onion forums matching a query via several onion search indexes (reached
through Tor), fetches public discussion pages, extracts text, and returns engine
records. Opt-in: needs `tor` installed, and it starts and stops its OWN ephemeral
Tor, never a system service.

What it will NOT do, enforced in code rather than promised:
  - no markets, no credentials/breach data, no CC/stolen goods, no CSAM, no weapons
  - a non-optional content filter drops any result signalling those categories
  - read-only: no login, no posting, no account creation, no purchases
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.parse

from .engine.core import dedup, rec

# Ahmia's v3 onion service, reached through our own Tor tunnel.
AHMIA = "juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion"

# Non-optional exclusion filter. A result matching any of these in its title, URL
# or body is dropped and counted, never returned. This keeps the tool
# information-only; there is deliberately no flag to disable it.
EXCLUDE = re.compile(
    r"\b("
    r"market(place)?|escrow|vendor|for\s?sale|carding|cvv|fullz|dumps?|"
    r"cc\s?shop|bank\s?logs?|paypal\s?log|combolist|stealer|"
    r"cocaine|heroin|meth|mdma|lsd|cannabis|weed|fentanyl|"
    r"counterfeit|passport|driver.?licen|ssn|"
    r"hitman|weapon|firearm|glock|ammunition|"
    r"cp\b|child|jailbait|loli|pedo"
    r")\b",
    re.I,
)

UA = "Mozilla/5.0 (Windows NT 10.0; rv:115.0) Gecko/20100101 Firefox/115.0"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _port_open(port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout):
            return True
    except OSError:
        return False


class Tor:
    """An ephemeral Tor process we own start to finish. Guarantees teardown even on
    exception, kills only our own child by PID, and verifies the kill."""

    def __init__(self, boot_timeout: int = 180, log=None):
        self.port = _free_port()
        self.datadir = tempfile.mkdtemp(prefix="dw-tor-")
        self.boot_timeout = boot_timeout
        self.proc = None
        self.log = log if log is not None else []

    def __enter__(self):
        if not shutil.which("tor"):
            shutil.rmtree(self.datadir, ignore_errors=True)
            raise RuntimeError(
                "tor is not installed. Install it (it is NOT left running):\n"
                "  brew install tor   (macOS)   /   sudo apt install tor   (Linux)\n"
                "This tool starts and stops its own Tor; do not run it as a service."
            )
        self.proc = subprocess.Popen(
            [
                "tor",
                "--SocksPort",
                str(self.port),
                "--DataDirectory",
                self.datadir,
                "--ControlPort",
                "0",
                "--ClientOnly",
                "1",
                "--AvoidDiskWrites",
                "1",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + self.boot_timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                self.stop()
                raise RuntimeError("tor exited during bootstrap")
            if _port_open(self.port):
                chk = _curl("https://check.torproject.org/api/ip", self.port, timeout=15)
                if chk and '"IsTor":true' in chk.replace(" ", ""):
                    self.log.append(f"tor up on 127.0.0.1:{self.port} (circuit confirmed)")
                    return self
            time.sleep(2)
        self.stop()
        raise RuntimeError(f"tor did not bootstrap within {self.boot_timeout}s")

    def __exit__(self, *exc):
        self.stop()
        return False

    def stop(self):
        """Kill our Tor and prove it is gone. Every check is logged."""
        if not self.proc:
            shutil.rmtree(self.datadir, ignore_errors=True)
            return True
        pid = self.proc.pid
        try:
            self.proc.terminate()
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                self.proc.kill()
                self.proc.wait(timeout=8)
            except Exception:
                pass
        except Exception:
            pass
        reaped = self.proc.poll() is not None
        try:
            os.kill(pid, 0)
            pid_gone = False
        except (ProcessLookupError, OSError):
            pid_gone = True
        if not (reaped and pid_gone):
            try:
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)
            except OSError:
                pass
            try:
                os.kill(pid, 0)
                pid_gone = False
            except OSError:
                pid_gone = True
        port_closed = not _port_open(self.port)
        shutil.rmtree(self.datadir, ignore_errors=True)
        dir_gone = not os.path.exists(self.datadir)
        ok = pid_gone and port_closed and dir_gone
        self.log.append(
            f"tor stopped: pid_gone={pid_gone} port_closed={port_closed} datadir_removed={dir_gone}"
            + ("" if ok else "  *** TEARDOWN INCOMPLETE - CHECK MANUALLY ***")
        )
        self.proc = None
        return ok


def _curl(url: str, port: int, timeout: int = 60) -> str:
    """Fetch through Tor. `--socks5-hostname` resolves the name INSIDE Tor, so no
    onion address or DNS query leaks to the local resolver."""
    try:
        r = subprocess.run(
            [
                "curl",
                "-s",
                "--max-time",
                str(timeout),
                "--socks5-hostname",
                f"127.0.0.1:{port}",
                "-A",
                UA,
                url,
            ],
            capture_output=True,
            timeout=timeout + 10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""


INDEXES = [
    ("ahmia", "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?q="),
    (
        "torch",
        "http://torchdeedp3i2jigzjdmfpn5ttjhthh5wbmda2rr3jvqjg5p77c54dqd.onion/search?query=",
    ),
    ("tordex", "http://tordexu73joywapk2txdr54jed4imqledpcvcuf75qsas2gwdgksvnyd.onion/?q="),
    ("tor66", "http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search?q="),
]

SEED_FORUMS = [
    ("Dread", "http://dreadytofatroptsdj6io7l3xptbet6onoyno2yv7jicoxknyazubrad.onion"),
]


def _parse_onions(html: str):
    """Pull every onion address plus nearby readable text, format-agnostic."""
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html)
    out, seen = [], set()
    onion_re = re.compile(r"(?:https?://)?([a-z2-7]{56}\.onion)([/][^\s<>\"']*)?")
    for m in onion_re.finditer(text):
        onion = m.group(1)
        if onion in seen:
            continue
        seen.add(onion)
        window = text[max(0, m.start() - 200) : m.end() + 200]
        window = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", window)).strip()
        out.append((f"http://{onion}", "", window))
    return out


def search_indexes(query: str, port: int, log: list, retries: int = 2):
    results, seen = [], set()
    for name, base in INDEXES:
        html = ""
        for _ in range(retries):
            html = _curl(base + urllib.parse.quote(query), port, timeout=70)
            if html:
                break
        if not html:
            log.append(f"{name}: no response (onion slow/down)")
            continue
        added = 0
        for url, title, snip in _parse_onions(html):
            if url in seen:
                continue
            seen.add(url)
            results.append((url, title, snip))
            added += 1
        log.append(f"{name}: {added} onion results")
    return results


def excluded(title: str, url: str, text: str) -> bool:
    return bool(EXCLUDE.search(f"{title} {url} {text}"))


def darkweb(query: str, fetch: int = 0, boot_timeout: int = 90):
    """Returns (records, log). Raises RuntimeError if tor is missing or won't boot."""
    log: list = []
    records, skipped = [], 0
    with Tor(boot_timeout=boot_timeout, log=log) as tor:
        hits = search_indexes(query, tor.port, log)
        hit_urls = {u for u, _, _ in hits}
        for name, u in SEED_FORUMS:
            if u not in hit_urls:
                hits.append((u, name, "known discussion forum (seed)"))
        for onion_url, title, snip in hits:
            if excluded(title, onion_url, snip):
                skipped += 1
                continue
            records.append(
                rec(
                    "darkweb", onion_url, onion_url, "", f"{title}\n{snip}", None, {"kind": "index"}
                )
            )
        for onion_url, title, _ in [(u, t, s) for u, t, s in hits if not excluded(t, u, s)][:fetch]:
            page = _curl(onion_url, tor.port, timeout=60)
            if not page:
                continue
            text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", page)
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()
            if excluded(title, onion_url, text):
                skipped += 1
                continue
            records.append(
                rec(
                    "darkweb",
                    onion_url + "#page",
                    onion_url,
                    "",
                    text[:4000],
                    None,
                    {"kind": "page"},
                )
            )
    if skipped:
        log.append(f"excluded (markets/credentials/illegal categories): {skipped}")
    records = dedup(records, log=log)
    return records, log


def tor_available() -> bool:
    return shutil.which("tor") is not None


def selftest():
    assert not excluded("Privacy tools discussion", "http://x.onion", "how to harden your setup")
    assert excluded("CC shop fresh fullz", "http://x.onion", "buy dumps")
    assert excluded("harmless title", "http://market.onion", "escrow vendor")
    assert excluded("t", "http://x.onion", "selling cocaine and weed")

    log = []
    t = Tor.__new__(Tor)
    t.port = _free_port()
    t.datadir = tempfile.mkdtemp(prefix="dw-test-")
    t.log = log
    t.proc = subprocess.Popen(["sleep", "60"])
    pid = t.proc.pid
    t.stop()
    try:
        os.kill(pid, 0)
        alive = True
    except OSError:
        alive = False
    assert not alive, "teardown left the process alive"
    assert not os.path.exists(t.datadir), "teardown left the datadir"
    assert any("pid_gone=True" in line for line in log), "teardown did not log its checks"
    print("darkweb.selftest ok")


if __name__ == "__main__":
    selftest()
