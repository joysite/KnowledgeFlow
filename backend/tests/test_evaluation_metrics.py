"""KnowledgeFlow 检索评估指标测试。"""

import pytest

from app.evaluation import (
    evaluate_ranking,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
)


def test_ideal_ranking_returns_perfect_metrics():
    """理想排序应当获得满分。"""
    metrics = evaluate_ranking(
        [2, 5, 8],
        {2: 2, 5: 1, 8: 1},
        k=3,
    )

    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.mrr == 1.0
    assert metrics.ndcg == pytest.approx(1.0)


def test_relevant_results_ranked_later_reduce_metrics():
    """相关结果排名靠后时，排序指标应下降。"""
    relevance = {2: 2, 5: 1, 8: 1}

    ideal = evaluate_ranking([2, 5, 8, 9], relevance, k=4)
    degraded = evaluate_ranking([9, 2, 5, 8], relevance, k=4)

    assert degraded.mrr < ideal.mrr
    assert degraded.ndcg < ideal.ndcg
    assert degraded.recall == ideal.recall


def test_precision_uses_k_as_denominator_when_results_are_insufficient():
    """结果不足 K 条时，Precision 分母仍为 K。"""
    assert precision_at_k([2, 9], {2: 1}, k=5) == pytest.approx(0.2)


def test_recall_counts_all_annotated_relevant_chunks():
    """Recall 分母包含全部已标注相关分块。"""
    assert recall_at_k([2, 9], {2: 1, 5: 2, 8: 1}, k=2) == pytest.approx(1 / 3)


def test_reciprocal_rank_uses_first_relevant_result():
    """MRR 使用首个相关结果的排名。"""
    assert reciprocal_rank_at_k([9, 5, 2], {2: 2, 5: 1}, k=3) == pytest.approx(0.5)


def test_ndcg_uses_relevance_grades():
    """nDCG 能区分不同相关性等级。"""
    relevance = {2: 2, 5: 1}

    best = ndcg_at_k([2, 5], relevance, k=2)
    worse = ndcg_at_k([5, 2], relevance, k=2)

    assert best == pytest.approx(1.0)
    assert 0 < worse < best


def test_empty_results_return_zero_metrics():
    """空检索结果返回零指标。"""
    metrics = evaluate_ranking([], {2: 2}, k=5)

    assert metrics.precision == 0.0
    assert metrics.recall == 0.0
    assert metrics.mrr == 0.0
    assert metrics.ndcg == 0.0


def test_no_relevant_chunks_return_zero_metrics():
    """没有相关标注时返回零指标。"""
    metrics = evaluate_ranking([2, 5], {2: 0, 5: 0}, k=2)

    assert metrics.precision == 0.0
    assert metrics.recall == 0.0
    assert metrics.mrr == 0.0
    assert metrics.ndcg == 0.0


@pytest.mark.parametrize(
    ("ranked_ids", "relevance", "k", "error"),
    [
        ([1, 1], {1: 1}, 5, ValueError),
        ([0], {1: 1}, 5, ValueError),
        ([True], {1: 1}, 5, TypeError),
        ([1], {1: 3}, 5, ValueError),
        ([1], {1: True}, 5, TypeError),
        ([1], {1: 1}, 0, ValueError),
        ([1], {1: 1}, True, TypeError),
    ],
)
def test_invalid_inputs_are_rejected(ranked_ids, relevance, k, error):
    """非法输入应当明确报错。"""
    with pytest.raises(error):
        evaluate_ranking(ranked_ids, relevance, k)
