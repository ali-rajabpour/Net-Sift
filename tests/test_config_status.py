from net_sift import config, status
from net_sift.access import opencli


def test_secret_env_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "_SECRETS", tmp_path / "secrets.json")
    monkeypatch.delenv("HIKERAPI_KEY", raising=False)
    assert config.get_secret("HIKERAPI_KEY") is None
    config.set_secret("HIKERAPI_KEY", "from-file")
    assert config.get_secret("HIKERAPI_KEY") == "from-file"
    monkeypatch.setenv("HIKERAPI_KEY", "from-env")
    assert config.get_secret("HIKERAPI_KEY") == "from-env"  # env wins


def test_status_badge(monkeypatch):
    monkeypatch.setattr(opencli, "available_cached", lambda ttl=60: True)
    line = status.line()
    assert "[NET-SIFT]" in line
    assert "web sources ready" in line


def test_secret_file_is_0600(tmp_path, monkeypatch):
    import stat as _stat

    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "_SECRETS", tmp_path / "secrets.json")
    config.set_secret("HIKERAPI_KEY", "x")
    mode = _stat.S_IMODE((tmp_path / "secrets.json").stat().st_mode)
    assert mode == 0o600


def test_fetch_ssrf_guard():
    from net_sift import mcp_server as m

    assert m._public_http_url("http://127.0.0.1/") is not None
    assert m._public_http_url("http://169.254.169.254/latest/meta-data") is not None
    assert m._public_http_url("http://10.0.0.5/") is not None
    assert m._public_http_url("file:///etc/passwd") is not None
    assert m._public_http_url("http://8.8.8.8/") is None  # public IP ok
