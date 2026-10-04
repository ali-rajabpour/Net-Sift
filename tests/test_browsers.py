from net_sift.access import browsers


def test_detect_only_present(tmp_path, monkeypatch):
    exe = tmp_path / "Chrome"
    exe.write_text("")
    prof = tmp_path / "prof"
    (prof / "Default").mkdir(parents=True)
    monkeypatch.setattr(
        browsers, "MAC_BROWSERS", {"chrome": ("Google Chrome", str(exe), str(prof))}
    )
    d = browsers.detect()
    assert set(d) == {"chrome"}
    assert d["chrome"]["executable"] == str(exe)
    assert d["chrome"]["source_profile"] == str(prof)


def test_detect_skips_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        browsers,
        "MAC_BROWSERS",
        {"ghost": ("Ghost", str(tmp_path / "nope"), str(tmp_path / "nope"))},
    )
    assert browsers.detect() == {}
