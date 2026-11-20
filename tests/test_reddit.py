import json
from html import escape

from net_sift.access import reddit


def _ctx(kind: str | None = None) -> str:
    ctx = {
        "action_info": {"position": 0, **({"type": kind} if kind else {})},
        "post": {"id": "t3_abc123", "title": "Fake post title", "nsfw": False},
        "profile": {"name": "fake_author"},
        "subreddit": {"name": "FakeSub"},
    }
    return escape(json.dumps(ctx))


# Shaped like a rendered search result: nested trackers sharing one post context.
FIXTURE = f"""
<search-telemetry-tracker data-faceplate-tracking-context="{escape(json.dumps({"action_info": {"type": "posts"}}))}">
  <a href="/search/?type=posts">Posts</a>
</search-telemetry-tracker>
<search-telemetry-tracker data-faceplate-tracking-context="{_ctx()}">
  <search-telemetry-tracker data-faceplate-tracking-context="{_ctx("post")}">
    <h2><a data-testid="post-title" href="/r/FakeSub/comments/abc123/fake_post_title/">Fake post title</a></h2>
  </search-telemetry-tracker>
  <img src="x.png">
  <faceplate-timeago ts="2026-01-02T03:04:05.000000+0000"><time>1d ago</time></faceplate-timeago>
  <div data-testid="search-counter-row">
    <faceplate-number number="42">42</faceplate-number> votes
    <faceplate-number number="7">7</faceplate-number> comments
  </div>
  <search-telemetry-tracker data-faceplate-tracking-context="{_ctx("snippet")}">
    <a>Body snippet text</a>
  </search-telemetry-tracker>
</search-telemetry-tracker>
"""


def test_parse_search_results():
    [r] = reddit.parse(FIXTURE)
    assert r["id"] == "reddit:abc123"
    assert r["url"] == "https://www.reddit.com/r/FakeSub/comments/abc123/fake_post_title/"
    assert r["author"] == "fake_author" and r["subreddit"] == "FakeSub"
    assert r["text"] == "Fake post title\nBody snippet text"
    assert r["created_at"].startswith("2026-01-02T03:04:05")
    assert r["score"] == 42 and r["comments"] == 7


def test_blocked_detector():
    assert reddit.blocked("Reddit - Prove your humanity", "")
    assert reddit.blocked("", "You've been blocked by network security.")
    assert not reddit.blocked("claude code - Reddit Search!", "results")
