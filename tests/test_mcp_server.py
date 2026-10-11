import asyncio
import time

from net_sift import mcp_server


class FakeCtx:
    def __init__(self):
        self.beats = []

    async def report_progress(self, progress, total=None, message=None):
        self.beats.append(progress)


def test_long_reports_progress_while_blocking(monkeypatch):
    monkeypatch.setattr(mcp_server, "HEARTBEAT", 0.02)
    ctx = FakeCtx()

    def slow(x, y=0):
        time.sleep(0.2)
        return x + y

    assert asyncio.run(mcp_server._long(ctx, slow, 1, y=2)) == 3
    assert len(ctx.beats) >= 2


def test_long_survives_failed_notification(monkeypatch):
    monkeypatch.setattr(mcp_server, "HEARTBEAT", 0.02)

    class Broken:
        async def report_progress(self, *a, **k):
            raise RuntimeError("client went away")

    def slow():
        time.sleep(0.1)
        return "done"

    assert asyncio.run(mcp_server._long(Broken(), slow)) == "done"


def test_context_is_not_a_tool_argument():
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    for name in ("deep_search", "resume", "doctor", "darkweb_search"):
        assert "ctx" not in tools[name].input_schema["properties"]
    assert tools["deep_search"].input_schema["required"] == ["query"]
