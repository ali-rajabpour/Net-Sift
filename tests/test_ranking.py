from net_sift.engine import ranking


def test_ranking_demo():
    ranking.demo()  # self-contained assertions


def test_phrase_beats_partial():
    assert ranking.relevance("tron blockchain", "tron blockchain upgrade") == 1.0
    assert ranking.relevance("tron blockchain", "a blockchain primer") < 0.6


def test_grounding_demotes_off_entity():
    recs = [
        {"text": "tron network news", "created_at": None},
        {"text": "ethereum network news", "created_at": None},
    ]
    ranked, _ = ranking.rank(recs, "tron network", floor=0.0)
    assert ranked[0]["text"].startswith("tron")
    assert ranked[-1]["_relevance"] < ranking.RELEVANCE_FLOOR


def test_cjk_segmentation():
    assert ranking.segment("大模型评测") != ["大模型评测"]
    assert ranking.relevance("大模型", "国产大模型评测") > 0.0
