from net_sift import config, status


def test_secret_env_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "_SECRETS", tmp_path / "secrets.json")
    monkeypatch.delenv("HIKERAPI_KEY", raising=False)
    assert config.get_secret("HIKERAPI_KEY") is None
    config.set_secret("HIKERAPI_KEY", "from-file")
    assert config.get_secret("HIKERAPI_KEY") == "from-file"
    monkeypatch.setenv("HIKERAPI_KEY", "from-env")
    assert config.get_secret("HIKERAPI_KEY") == "from-env"  # env wins


def test_status_badge_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(status.config, "get_browser_choice", lambda home: "comet")
    md = tmp_path / "profiles" / "comet"
    md.mkdir(parents=True)
    monkeypatch.setattr(status.profile, "logged_in", lambda p: {"twitter": True, "reddit": False})
    line = status.line()
    assert "[NET-SIFT]" in line
    assert "web sources ready" in line
    assert "1 accounts" in line


def test_status_badge_no_profile(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(status.config, "get_browser_choice", lambda home: None)
    line = status.line()
    assert "[NET-SIFT]" in line
    assert "no profile" in line


def test_secret_file_is_0600(tmp_path, monkeypatch):
    import stat as _stat

    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "_SECRETS", tmp_path / "secrets.json")
    config.set_secret("HIKERAPI_KEY", "x")
    mode = _stat.S_IMODE((tmp_path / "secrets.json").stat().st_mode)
    assert mode == 0o600
