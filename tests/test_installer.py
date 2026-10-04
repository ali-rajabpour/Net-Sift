import json

from net_sift import installer


def test_parse_version():
    assert installer.parse_version("v26.9.0") == (26, 9, 0)
    assert installer.parse_version("node 20.18.1") == (20, 18, 1)
    assert installer.parse_version("garbage") == (0,)


def test_node_ok():
    assert installer.node_ok("v20.18.1") is True
    assert installer.node_ok("v26.9.0") is True
    assert installer.node_ok("v18.0.0") is False
    assert installer.node_ok("v20.18.0") is False


def test_compose_statusline_no_existing(tmp_path):
    p = tmp_path / "settings.json"
    ui = installer._UI(assume_yes=True)
    msg = installer.compose_statusline(p, tmp_path, ui)
    assert "status bar set" in msg
    assert json.loads(p.read_text())["statusLine"]["command"] == "net-sift status --line"


def test_compose_statusline_wraps_existing(tmp_path):
    p = tmp_path / "settings.json"
    orig = {"type": "command", "command": 'bash "/x/caveman.sh"'}
    p.write_text(json.dumps({"statusLine": orig}))
    ui = installer._UI(assume_yes=True)  # confirm -> yes
    msg = installer.compose_statusline(p, tmp_path, ui)
    assert "added a net-sift line" in msg
    wrap = installer._nsift_dir(tmp_path) / "statusline-wrap.sh"
    assert wrap.exists()
    body = wrap.read_text()
    assert 'bash "/x/caveman.sh"' in body and "net-sift status --line" in body
    # original preserved for restore
    prev = json.loads((installer._nsift_dir(tmp_path) / "statusline-prev.json").read_text())
    assert prev == orig
    assert "statusline-wrap.sh" in json.loads(p.read_text())["statusLine"]["command"]


def test_detect_clients(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.shutil, "which", lambda _x: None)
    assert installer.detect_clients(tmp_path) == {"claude": False, "codex": False}
    (tmp_path / ".claude.json").write_text("{}")
    (tmp_path / ".codex").mkdir()
    d = installer.detect_clients(tmp_path)
    assert d["claude"] and d["codex"]


def test_run_wizard_all_present(tmp_path, monkeypatch, capsys):
    # everything already installed; one browser detected and copied -> wizard completes
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(installer, "_run", lambda cmd, timeout=300: (0, "v26.9.0"))
    monkeypatch.setattr(
        installer.browsers,
        "detect",
        lambda: {
            "comet": {"id": "comet", "name": "Comet", "executable": "/x", "source_profile": "/s"}
        },
    )
    monkeypatch.setattr(installer.profile, "logged_in", lambda p: {"twitter": True, "reddit": True})
    monkeypatch.setattr(installer.profile, "copy_profile", lambda src, dst: dst)
    (tmp_path / ".claude.json").write_text("{}")
    rc = installer.run(tmp_path, assume_yes=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Node v26.9.0 present" in out
    assert "OpenCLI already installed" in out
    assert "Copied Comet" in out
    assert "net-sift is installed" in out
