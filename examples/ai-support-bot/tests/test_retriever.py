from support_bot.retriever import DOCS, retrieve, tokenize


def test_corpus_has_policy_documents():
    assert {"refunds.md", "shipping.md", "warranty.md", "returns.md"} <= set(DOCS)


def test_tokenize_lowercases_and_drops_stopwords():
    assert tokenize("How LONG does Standard Shipping take") == ["long", "standard", "shipping", "take"]


def test_returns_at_most_k_results():
    assert len(retrieve("refund shipping warranty payment account", k=2)) <= 2


def test_results_are_corpus_documents():
    for doc_id, score, text in retrieve("standard shipping", k=3):
        assert doc_id in DOCS
        assert score > 0
        assert text == DOCS[doc_id]


def test_standard_shipping_ranks_shipping_doc_first():
    assert retrieve("standard shipping")[0][0] == "shipping.md"


def test_scores_are_sorted_descending():
    scores = [score for _doc_id, score, _text in retrieve("refund for a damaged item")]
    assert scores == sorted(scores, reverse=True)


def test_unrelated_query_returns_nothing():
    assert retrieve("quantum chromodynamics lecture") == []
