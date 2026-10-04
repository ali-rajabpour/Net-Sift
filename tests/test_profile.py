import sqlite3
import stat
from pathlib import Path

from net_sift.access import profile


def _cookies_db(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("create table cookies (host_key text, name text, encrypted_value blob)")
    c.executemany("insert into cookies values (?,?,?)", rows)
    c.commit()
    c.close()


def test_copy_profile_0700_and_readonly_source(tmp_path):
    src = tmp_path / "src"
    (src / "Default").mkdir(parents=True)
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
    _cookies_db(
        prof / "Default" / "Cookies",
        [(".x.com", "auth_token", b""), (".reddit.com", "reddit_session", b"")],
    )
    st = profile.logged_in(str(prof))
    assert st["twitter"] is True and st["reddit"] is True
    assert st["zhihu"] is False


def test_logged_in_missing_db(tmp_path):
    assert profile.logged_in(str(tmp_path / "none")) == {k: False for k in profile.AUTH_COOKIES}
