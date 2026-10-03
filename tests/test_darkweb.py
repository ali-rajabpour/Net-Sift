from net_sift import darkweb


def test_exclude_filter():
    assert not darkweb.excluded("Privacy tools discussion", "http://x.onion", "harden your setup")
    assert darkweb.excluded("CC shop fresh fullz", "http://x.onion", "buy dumps")
    assert darkweb.excluded("harmless", "http://market.onion", "escrow vendor")
    assert darkweb.excluded("t", "http://x.onion", "selling cocaine and weed")


def test_parse_onions():
    html = "see http://abc.onion and <a>juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/x</a>"
    hits = darkweb._parse_onions(html)
    urls = [u for u, _, _ in hits]
    assert any(".onion" in u for u in urls)


def test_selftest_teardown():
    darkweb.selftest()  # spawns a stand-in proc, proves teardown, no network/tor
