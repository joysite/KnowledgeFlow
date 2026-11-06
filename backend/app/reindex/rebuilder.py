"""KnowledgeFlow 临时向量索引重建服务。"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings import EmbeddingService
from app.reindex.auditor import VectorIndexAuditor, VectorIndexAuditReport
from app.repositories import DocumentChunkRepository, KnowledgeBaseRepository
from app.services.vector_index import VectorIndexService
from app.vectorstore.chroma import ChromaVectorStore


@dataclass
class VectorIndexRebuildReport:
    """向量索引重建结果。"""

    knowledge_base_id: int
    collection_name: str
    indexed_chunk_count: int
    page_count: int
    audit_report: VectorIndexAuditReport

    @property
    def is_consistent(self) -> bool:
        """判断重建结果是否通过一致性审计。"""
        return self.audit_report.is_consistent


class VectorIndexRebuilder:
    """将 SQLite 分块分页重建到独立的 Chroma 集合。"""

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingService,
        vector_store: ChromaVectorStore,
    ) -> None:
        """初始化重建服务。"""
        self.session = session
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    async def rebuild(
        self,
        knowledge_base_id: int,
        collection_name: str,
        page_size: int = 100,
        index_batch_size: int = 32,
    ) -> VectorIndexRebuildReport:
        """分页重建临时集合并执行一致性审计。"""
        if isinstance(knowledge_base_id, bool) or not isinstance(knowledge_base_id, int):
            raise TypeError("knowledge_base_id 必须是整数")
        if knowledge_base_id <= 0:
            raise ValueError("knowledge_base_id 必须大于 0")

        if not isinstance(collection_name, str):
            raise TypeError("collection_name 必须是字符串")
        if not collection_name.strip():
            raise ValueError("collection_name 不能为空")

        for name, value in (
            ("page_size", page_size),
            ("index_batch_size", index_batch_size),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} 必须是整数")
            if value <= 0:
                raise ValueError(f"{name} 必须大于 0")

        knowledge_base = await KnowledgeBaseRepository(self.session).get_by_id(knowledge_base_id)
        if knowledge_base is None:
            raise ValueError(f"知识库不存在: {knowledge_base_id}")

        existing_names = {
            getattr(item, "name", item) for item in self.vector_store.client.list_collections()
        }
        if collection_name in existing_names:
            raise ValueError(f"目标集合已存在，拒绝覆盖: {collection_name}")

        repository = DocumentChunkRepository(self.session)
        index_service = VectorIndexService(
            self.embedding_service,
            self.vector_store,
            batch_size=index_batch_size,
            collection_name=collection_name,
        )

        indexed_chunk_count = 0
        page_count = 0
        offset = 0

        while True:
            chunks = await repository.get_by_knowledge_base(
                knowledge_base_id,
                offset=offset,
                limit=page_size,
            )

            if not chunks:
                break

            await index_service.index_chunks(chunks, knowledge_base_id)

            indexed_chunk_count += len(chunks)
            page_count += 1
            offset += len(chunks)

            if len(chunks) < page_size:
                break

        # 空知识库也需要一个真实存在的空集合，才能完成审计。
        if page_count == 0:
            self.vector_store.get_or_create_collection(collection_name)

        audit_report = await VectorIndexAuditor(
            self.session,
            self.vector_store,
        ).audit(
            knowledge_base_id,
            batch_size=page_size,
            collection_name=collection_name,
        )

        return VectorIndexRebuildReport(
            knowledge_base_id=knowledge_base_id,
            collection_name=collection_name,
            indexed_chunk_count=indexed_chunk_count,
            page_count=page_count,
            audit_report=audit_report,
        )
