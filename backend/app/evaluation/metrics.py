"""KnowledgeFlow 检索评估指标。"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    """单条查询的检索评估结果。"""

    precision: float
    recall: float
    mrr: float
    ndcg: float


def _validate_inputs(
    ranked_chunk_ids: Sequence[int],
    relevance: Mapping[int, int],
    k: int,
) -> None:
    """校验排名结果、相关性标注和 K 值。"""
    if not isinstance(ranked_chunk_ids, Sequence) or isinstance(ranked_chunk_ids, (str, bytes)):
        raise TypeError("ranked_chunk_ids 必须是整数序列")

    seen: set[int] = set()
    for chunk_id in ranked_chunk_ids:
        if isinstance(chunk_id, bool) or not isinstance(chunk_id, int):
            raise TypeError("chunk_id 必须是整数")
        if chunk_id <= 0:
            raise ValueError("chunk_id 必须大于 0")
        if chunk_id in seen:
            raise ValueError("检索结果中不能包含重复 chunk_id")
        seen.add(chunk_id)

    if not isinstance(relevance, Mapping):
        raise TypeError("relevance 必须是映射类型")

    for chunk_id, grade in relevance.items():
        if isinstance(chunk_id, bool) or not isinstance(chunk_id, int):
            raise TypeError("相关性标注的 chunk_id 必须是整数")
        if chunk_id <= 0:
            raise ValueError("相关性标注的 chunk_id 必须大于 0")
        if isinstance(grade, bool) or not isinstance(grade, int):
            raise TypeError("相关性等级必须是整数")
        if grade not in (0, 1, 2):
            raise ValueError("相关性等级只能是 0、1 或 2")

    if isinstance(k, bool) or not isinstance(k, int):
        raise TypeError("k 必须是整数")
    if k <= 0:
        raise ValueError("k 必须大于 0")


def precision_at_k(
    ranked_chunk_ids: Sequence[int],
    relevance: Mapping[int, int],
    k: int = 5,
) -> float:
    """计算 Precision@K，分母固定为 K。"""
    _validate_inputs(ranked_chunk_ids, relevance, k)
    relevant_count = sum(relevance.get(chunk_id, 0) > 0 for chunk_id in ranked_chunk_ids[:k])
    return relevant_count / k


def recall_at_k(
    ranked_chunk_ids: Sequence[int],
    relevance: Mapping[int, int],
    k: int = 5,
) -> float:
    """计算 Recall@K。"""
    _validate_inputs(ranked_chunk_ids, relevance, k)
    total_relevant = sum(grade > 0 for grade in relevance.values())
    if total_relevant == 0:
        return 0.0

    retrieved_relevant = sum(relevance.get(chunk_id, 0) > 0 for chunk_id in ranked_chunk_ids[:k])
    return retrieved_relevant / total_relevant


def reciprocal_rank_at_k(
    ranked_chunk_ids: Sequence[int],
    relevance: Mapping[int, int],
    k: int = 5,
) -> float:
    """计算 Reciprocal Rank@K。"""
    _validate_inputs(ranked_chunk_ids, relevance, k)
    for rank, chunk_id in enumerate(ranked_chunk_ids[:k], start=1):
        if relevance.get(chunk_id, 0) > 0:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    ranked_chunk_ids: Sequence[int],
    relevance: Mapping[int, int],
    k: int = 5,
) -> float:
    """计算基于 0～2 级相关性标注的 nDCG@K。"""
    _validate_inputs(ranked_chunk_ids, relevance, k)

    def gain(grade: int) -> float:
        return float(2**grade - 1)

    actual_dcg = sum(
        gain(relevance.get(chunk_id, 0)) / math.log2(rank + 1)
        for rank, chunk_id in enumerate(ranked_chunk_ids[:k], start=1)
    )
    ideal_grades = sorted(relevance.values(), reverse=True)[:k]
    ideal_dcg = sum(
        gain(grade) / math.log2(rank + 1) for rank, grade in enumerate(ideal_grades, start=1)
    )
    if ideal_dcg == 0:
        return 0.0
    return actual_dcg / ideal_dcg


def evaluate_ranking(
    ranked_chunk_ids: Sequence[int],
    relevance: Mapping[int, int],
    k: int = 5,
) -> RetrievalMetrics:
    """一次性计算单条查询的全部检索指标。"""
    _validate_inputs(ranked_chunk_ids, relevance, k)
    return RetrievalMetrics(
        precision=precision_at_k(ranked_chunk_ids, relevance, k),
        recall=recall_at_k(ranked_chunk_ids, relevance, k),
        mrr=reciprocal_rank_at_k(ranked_chunk_ids, relevance, k),
        ndcg=ndcg_at_k(ranked_chunk_ids, relevance, k),
    )
