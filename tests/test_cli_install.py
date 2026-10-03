import json

from net_sift import cli


def test_merge_json_mcp_creates_and_is_idempotent(tmp_path):
    p = tmp_path / ".claude.json"
    msg1 = cli.merge_json_mcp(p)
    assert "registered" in msg1
    data = json.loads(p.read_text())
    assert data["mcpServers"]["net-sift"] == cli.MCP_ENTRY
    assert "already present" in cli.merge_json_mcp(p)


def test_merge_json_mcp_preserves_existing(tmp_path):
    p = tmp_path / ".claude.json"
    p.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "keep": 1}))
    cli.merge_json_mcp(p)
    data = json.loads(p.read_text())
    assert data["keep"] == 1
    assert "other" in data["mcpServers"] and "net-sift" in data["mcpServers"]


def test_ensure_statusline(tmp_path):
    p = tmp_path / "settings.json"
    cli.ensure_statusline(p)
    data = json.loads(p.read_text())
    assert data["statusLine"]["command"] == "net-sift status --line"
    assert "already set" in cli.ensure_statusline(p)


def test_ensure_statusline_never_clobbers_existing(tmp_path):
    p = tmp_path / "settings.json"
    mine = {"type": "command", "command": "bash /some/caveman-statusline.sh"}
    p.write_text(json.dumps({"statusLine": mine, "keep": 1}))
    msg = cli.ensure_statusline(p)
    assert "kept your existing" in msg
    data = json.loads(p.read_text())
    assert data["statusLine"] == mine  # untouched
    assert data["keep"] == 1


def test_ensure_codex_appends_once(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[existing]\nkey = 1\n")
    cli.ensure_codex(p)
    text = p.read_text()
    assert "[mcp_servers.net-sift]" in text and "[existing]" in text
    assert "already present" in cli.ensure_codex(p)
    assert p.read_text().count("[mcp_servers.net-sift]") == 1
