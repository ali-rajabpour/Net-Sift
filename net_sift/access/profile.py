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

# site id -> (host suffix, auth cookie names, any of which means logged in)
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

# Items under Default worth copying. Cookies live in Network/Cookies on current
# Chromium, Cookies on older builds; both are tried.
_DEFAULT_ITEMS = ("Network/Cookies", "Cookies", "Preferences", "Local Storage", "Login Data")


def managed_dir(home: Path, browser_id: str) -> Path:
    return Path(home) / "profiles" / browser_id


def copy_profile(source_profile: str, dest: str) -> str:
    """Copy Local State and the needed Default items into dest (created 0700).

    Safe to run while the source browser is live; the source is only read."""
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
        if not s.exists():
            continue
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
    """Per-site logged-in flags, read from cookie names only. Tolerant of a missing
    or browser-locked Cookies DB (returns all False rather than raising)."""
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
        out[site] = any(h.endswith(host) and n in cookie_names for h, n in names)
    return out
