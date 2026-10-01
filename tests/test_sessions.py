import pytest

from net_sift import config, sessions
from net_sift.engine import core


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "SESSIONS_DIR", tmp_path / "sessions")
    return tmp_path


def _recs():
    return [core.rec("github", str(i), "u", "a", f"tron item {i}", None) for i in range(5)]


def test_save_list_load_cleanup(tmp_home):
    meta = sessions.save("tron", {"platforms": ["github"]}, _recs(), ["github[0] 5 records"])
    assert meta["count"] == 5
    assert sessions.load_meta(meta["id"])["query"] == "tron"
    assert len(sessions.load_corpus(meta["id"])) == 5

    listed = sessions.list_sessions()
    assert len(listed) == 1 and listed[0]["id"] == meta["id"]

    assert sessions.cleanup(meta["id"]) is True
    assert sessions.load_meta(meta["id"]) is None
    assert sessions.list_sessions() == []


def test_cleanup_rejects_outside_path(tmp_home):
    assert sessions.cleanup("../../etc") is False


def test_seen_ids(tmp_home):
    meta = sessions.save("tron", {}, _recs(), [])
    assert sessions.seen_ids(meta["id"]) == {f"github:{i}" for i in range(5)}
