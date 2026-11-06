"""KnowledgeFlow Reciprocal Rank Fusion 排名融合算法。"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RRFResult:
    """RRF 融合结果。"""

    chunk_id: int
    score: float


class ReciprocalRankFusion:
    """融合多路检索结果的倒数排名算法。"""

    def __init__(self, k: int = 60) -> None:
        """初始化 RRF 算法。"""
        if isinstance(k, bool) or not isinstance(k, int):
            raise TypeError("k 必须是整数")
        if k <= 0:
            raise ValueError("k 必须大于 0")

        self.k = k

    def fuse(
        self,
        rankings: Sequence[Sequence[int]],
        top_k: int = 5,
    ) -> list[RRFResult]:
        """融合多路排名，返回分数最高的分块。"""
        if not isinstance(rankings, Sequence):
            raise TypeError("rankings 必须是序列")

        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k 必须是整数")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")

        scores: dict[int, float] = {}
        first_seen: dict[int, int] = {}
        order = 0

        for ranking in rankings:
            if not isinstance(ranking, Sequence):
                raise TypeError("每路排名必须是序列")

            seen: set[int] = set()

            for rank, chunk_id in enumerate(ranking, start=1):
                if isinstance(chunk_id, bool) or not isinstance(chunk_id, int):
                    raise TypeError("chunk_id 必须是整数")
                if chunk_id <= 0:
                    raise ValueError("chunk_id 必须大于 0")
                if chunk_id in seen:
                    continue

                seen.add(chunk_id)

                if chunk_id not in scores:
                    scores[chunk_id] = 0.0
                    first_seen[chunk_id] = order
                    order += 1

                scores[chunk_id] += 1.0 / (self.k + rank)

        results = [RRFResult(chunk_id=chunk_id, score=score) for chunk_id, score in scores.items()]

        results.sort(
            key=lambda item: (
                -item.score,
                first_seen[item.chunk_id],
            )
        )

        return results[:top_k]
