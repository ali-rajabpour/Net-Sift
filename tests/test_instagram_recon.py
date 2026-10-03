from net_sift import config
from net_sift import instagram_recon as ig


def test_ig_items_finds_media():
    payload = {
        "response": {
            "medias": [
                {"pk": "1", "code": "abc", "taken_at": 1700000000, "location": {"name": "Paris"}},
                {"wrapper": True},
            ]
        }
    }
    items = ig._ig_items(payload)
    assert len(items) == 1 and items[0]["code"] == "abc"


def test_key_present_and_run_without_key(monkeypatch):
    monkeypatch.setattr(config, "get_secret", lambda name: None)
    assert ig.key_present() is False
    out = ig.run("profile", "@nasa")
    assert "error" in out and "HikerAPI" in out["error"]


def test_run_unknown_op(monkeypatch):
    monkeypatch.setattr(config, "get_secret", lambda name: "k")
    out = ig.run("nope", "@nasa")
    assert "unknown op" in out["error"]


def test_max_requests_clamped(monkeypatch):
    monkeypatch.setattr(config, "get_secret", lambda name: "k")
    monkeypatch.setitem(ig.OPS, "probe", (lambda b, key, handle, **kw: {"cap": b.cap}, 1))
    out = ig.run("probe", "@x", max_requests=999999)
    assert out["cap"] == ig.MAX_REQUESTS_CEILING


def test_budget_caps(monkeypatch):
    b = ig.Budget(1)
    monkeypatch.setattr(ig, "_json", lambda url, headers: {"ok": True})
    b.get("/v1/x", "k")  # first ok
    try:
        b.get("/v1/x", "k")  # second exceeds cap
        raised = False
    except ig.RequestCapReached:
        raised = True
    assert raised
