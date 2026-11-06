"""KnowledgeFlow 混合检索服务。"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.retrieval.rrf import ReciprocalRankFusion
from app.services.bm25_search import BM25SearchService
from app.services.vector_search import VectorSearchService


@dataclass(frozen=True, slots=True)
class HybridSearchResult:
    """混合检索结果。"""

    chunk_id: int
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    token_count: int
    vector_distance: float | None
    bm25_score: float | None
    rrf_score: float


class HybridSearchService:
    """协调向量检索、BM25 检索和 RRF 排名融合。"""

    def __init__(
        self,
        session: AsyncSession,
        vector_search_service: VectorSearchService,
        bm25_search_service: BM25SearchService,
        fusion: ReciprocalRankFusion | None = None,
    ) -> None:
        """初始化混合检索服务。"""
        self.session = session
        self.vector_search_service = vector_search_service
        self.bm25_search_service = bm25_search_service
        self.fusion = fusion or ReciprocalRankFusion()

    @staticmethod
    def _validate_inputs(
        query: str,
        knowledge_base_id: int,
        top_k: int,
    ) -> None:
        """校验检索参数。"""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("查询文本不能为空")

        if isinstance(knowledge_base_id, bool) or not isinstance(knowledge_base_id, int):
            raise TypeError("knowledge_base_id 必须是整数")
        if knowledge_base_id <= 0:
            raise ValueError("knowledge_base_id 必须大于 0")

        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k 必须是整数")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")

    async def search(
        self,
        query: str,
        knowledge_base_id: int,
        top_k: int = 5,
    ) -> list[HybridSearchResult]:
        """执行双路召回并融合排名。"""
        self._validate_inputs(query, knowledge_base_id, top_k)

        candidate_top_k = top_k * 2

        # 两个检索服务共用当前请求的 AsyncSession，不能并发执行。
        vector_results = await self.vector_search_service.search(
            query=query,
            knowledge_base_id=knowledge_base_id,
            top_k=candidate_top_k,
        )
        bm25_results = await self.bm25_search_service.search(
            query=query,
            knowledge_base_id=knowledge_base_id,
            top_k=candidate_top_k,
        )

        vector_map = {item.chunk_id: item for item in vector_results}
        bm25_map = {item.chunk_id: item for item in bm25_results}

        rankings = [
            [item.chunk_id for item in vector_results],
            [item.chunk_id for item in bm25_results],
        ]
        fused_results = self.fusion.fuse(rankings, top_k=top_k)

        results = []

        for fused in fused_results:
            vector_item = vector_map.get(fused.chunk_id)
            bm25_item = bm25_map.get(fused.chunk_id)
            source = vector_item or bm25_item

            if source is None:
                continue

            results.append(
                HybridSearchResult(
                    chunk_id=source.chunk_id,
                    document_id=source.document_id,
                    document_name=source.document_name,
                    chunk_index=source.chunk_index,
                    content=source.content,
                    token_count=source.token_count,
                    vector_distance=(vector_item.distance if vector_item is not None else None),
                    bm25_score=(bm25_item.score if bm25_item is not None else None),
                    rrf_score=fused.score,
                )
            )

        return results
