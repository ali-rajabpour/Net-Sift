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


def test_detect_clients(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.shutil, "which", lambda _x: None)
    assert installer.detect_clients(tmp_path) == {"claude": False, "codex": False}
    (tmp_path / ".claude.json").write_text("{}")
    (tmp_path / ".codex").mkdir()
    d = installer.detect_clients(tmp_path)
    assert d["claude"] and d["codex"]


def test_run_wizard_all_present(tmp_path, monkeypatch, capsys):
    # everything already installed and connected -> wizard completes, no npm/brew calls
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(installer, "_run", lambda cmd, timeout=300: (0, "v26.9.0"))
    from net_sift.access import opencli

    monkeypatch.setattr(opencli, "available", lambda: True)
    monkeypatch.setattr(opencli, "probe_login", lambda site, timeout=60: True)
    (tmp_path / ".claude.json").write_text("{}")
    rc = installer.run(tmp_path, assume_yes=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Node v26.9.0 present" in out
    assert "OpenCLI already installed" in out
    assert "Browser connected" in out
    assert "Reddit: connected" in out
    assert "net-sift is installed" in out
