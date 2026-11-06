"""KnowledgeFlow 向量检索服务。"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings import EmbeddingService
from app.repositories import DocumentChunkRepository
from app.vectorstore.chroma import ChromaVectorStore


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    """向量检索结果。"""

    chunk_id: int
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    token_count: int
    distance: float


class VectorSearchService:
    """协调查询向量化、Chroma 召回和 SQLite 原文回查。"""

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingService,
        vector_store: ChromaVectorStore,
        collection_name: str | None = None,
    ) -> None:
        """初始化向量检索服务。"""
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        if collection_name is not None:
            if not isinstance(collection_name, str):
                raise TypeError("collection_name 必须是字符串")
            if not collection_name.strip():
                raise ValueError("collection_name 不能为空")
        self.collection_name = collection_name
        self.repository = DocumentChunkRepository(session)

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
    ) -> list[VectorSearchResult]:
        """检索指定知识库中的相似分块。"""
        self._validate_inputs(query, knowledge_base_id, top_k)

        embedding = await self.embedding_service.embed_text(query)

        collection_name = self.collection_name or f"knowledge_base_{knowledge_base_id}"
        vector_result = self.vector_store.query(
            collection_name=collection_name,
            query_embeddings=[embedding],
            n_results=top_k,
            where={"knowledge_base_id": knowledge_base_id},
        )

        result_ids = vector_result.get("ids")
        distances = vector_result.get("distances")

        if not isinstance(result_ids, list) or not result_ids:
            return []

        candidate_ids = result_ids[0]
        candidate_distances = distances[0] if isinstance(distances, list) and distances else []

        if not isinstance(candidate_ids, list) or not candidate_ids:
            return []

        # 保留 Chroma 召回顺序，并过滤无效 ID。
        ordered_candidates: list[tuple[int, float]] = []
        seen_ids: set[int] = set()

        for index, raw_id in enumerate(candidate_ids):
            try:
                chunk_id = int(raw_id)
            except (TypeError, ValueError):
                continue

            if chunk_id <= 0 or chunk_id in seen_ids:
                continue

            if index >= len(candidate_distances):
                continue

            distance = candidate_distances[index]
            if isinstance(distance, bool) or not isinstance(distance, (int, float)):
                continue

            seen_ids.add(chunk_id)
            ordered_candidates.append((chunk_id, float(distance)))

        if not ordered_candidates:
            return []

        chunks = await self.repository.get_by_ids(
            knowledge_base_id=knowledge_base_id,
            chunk_ids=[chunk_id for chunk_id, _ in ordered_candidates],
        )

        # SQLite 回查结果不保证顺序，按 Chroma 召回顺序重新组织。
        chunk_map = {chunk.id: chunk for chunk in chunks}

        results = []

        for chunk_id, distance in ordered_candidates:
            chunk = chunk_map.get(chunk_id)
            if chunk is None:
                continue

            results.append(
                VectorSearchResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_name=chunk.document.name,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    distance=distance,
                )
            )

        return results
