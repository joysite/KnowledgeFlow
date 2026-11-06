"""BM25 关键词检索算法测试。"""

import math

import pytest

from app.retrieval.bm25 import BM25Retriever


def test_bm25_ranks_matching_documents():
    """匹配查询词的文档应获得正分并排在前面。"""
    retriever = BM25Retriever(
        [
            ["python", "fastapi", "api"],
            ["java", "spring", "api"],
            ["python", "machine", "learning"],
        ]
    )

    results = retriever.search(["python"])

    assert [item.document_index for item in results] == [0, 2]
    assert all(item.score > 0 for item in results)


def test_bm25_uses_inverse_document_frequency():
    """低文档频率词应比高文档频率词具有更高 IDF。"""
    retriever = BM25Retriever(
        [
            ["rare", "common"],
            ["common", "other"],
            ["common", "another"],
        ]
    )

    assert (
        retriever.inverse_document_frequencies["rare"]
        > retriever.inverse_document_frequencies["common"]
    )


def test_bm25_uses_term_frequency():
    """其他条件相同时，合理增加词频应提高相关性分数。"""
    retriever = BM25Retriever(
        [
            ["python"],
            ["python", "python", "python"],
            ["java"],
        ]
    )

    results = retriever.search(["python"])

    assert results[0].document_index == 1
    assert results[0].score > results[1].score


def test_bm25_deduplicates_query_terms():
    """重复查询词不会重复累计权重。"""
    retriever = BM25Retriever([["python", "fastapi"], ["java"]])

    single = retriever.search(["python"])
    repeated = retriever.search(["python", "python"])

    assert single == repeated


def test_bm25_returns_empty_for_unmatched_query():
    """查询词不在语料中时返回空列表。"""
    retriever = BM25Retriever([["python"], ["java"]])

    assert retriever.search(["rust"]) == []
    assert retriever.search([]) == []


def test_bm25_respects_top_k():
    """检索结果数量不超过 Top-K。"""
    retriever = BM25Retriever([["python"], ["python", "api"], ["python", "fastapi"]])

    assert len(retriever.search(["python"], top_k=2)) == 2


def test_bm25_keeps_original_order_for_equal_scores():
    """分数相同时保持语料原始顺序。"""
    retriever = BM25Retriever([["python"], ["python"], ["java"]])

    results = retriever.search(["python"])

    assert [item.document_index for item in results] == [0, 1]


def test_bm25_returns_empty_for_empty_corpus():
    """空语料返回空结果。"""
    retriever = BM25Retriever([])

    assert retriever.search(["python"]) == []


def test_bm25_calculates_expected_score():
    """验证 BM25 分数符合 Okapi 公式。"""
    retriever = BM25Retriever(
        [["python", "api"], ["java", "api"]],
        k1=1.5,
        b=0.75,
    )

    result = retriever.search(["python"])[0]

    idf = math.log(1 + (2 - 1 + 0.5) / (1 + 0.5))
    expected = idf * (1 * (1.5 + 1)) / (1 + 1.5)

    assert result.document_index == 0
    assert result.score == pytest.approx(expected)


@pytest.mark.parametrize(
    ("k1", "b", "error"),
    [
        (0, 0.75, ValueError),
        (-1, 0.75, ValueError),
        (True, 0.75, TypeError),
        (1.5, -0.1, ValueError),
        (1.5, 1.1, ValueError),
        (1.5, True, TypeError),
    ],
)
def test_bm25_rejects_invalid_parameters(k1, b, error):
    """拒绝非法 BM25 参数。"""
    with pytest.raises(error):
        BM25Retriever([["python"]], k1=k1, b=b)


@pytest.mark.parametrize(
    ("query_tokens", "top_k", "error"),
    [
        ("python", 5, TypeError),
        ([1], 5, ValueError),
        ([""], 5, ValueError),
        (["python"], 0, ValueError),
        (["python"], True, TypeError),
    ],
)
def test_bm25_rejects_invalid_search_arguments(query_tokens, top_k, error):
    """拒绝非法查询参数。"""
    retriever = BM25Retriever([["python"]])

    with pytest.raises(error):
        retriever.search(query_tokens, top_k=top_k)


def test_bm25_rejects_invalid_corpus():
    """拒绝非法语料结构和 Token。"""
    with pytest.raises(TypeError):
        BM25Retriever("python")

    with pytest.raises(TypeError):
        BM25Retriever([None])

    with pytest.raises(ValueError):
        BM25Retriever([["python", ""]])
