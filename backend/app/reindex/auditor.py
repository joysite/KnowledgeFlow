"""KnowledgeFlow 向量索引一致性审计。"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import DocumentChunkRepository, KnowledgeBaseRepository
from app.vectorstore.chroma import ChromaVectorStore


@dataclass
class VectorIndexAuditReport:
    """向量索引一致性审计报告。"""

    knowledge_base_id: int
    knowledge_base_exists: bool
    collection_exists: bool
    sqlite_chunk_count: int
    chroma_vector_count: int
    missing_vector_ids: list[str]
    orphan_vector_ids: list[str]
    invalid_metadata_ids: list[str]

    @property
    def is_consistent(self) -> bool:
        """判断数据库与向量索引是否完全一致。"""
        return (
            self.knowledge_base_exists
            and self.collection_exists
            and not self.missing_vector_ids
            and not self.orphan_vector_ids
            and not self.invalid_metadata_ids
            and self.sqlite_chunk_count == self.chroma_vector_count
        )


class VectorIndexAuditor:
    """只读检查 SQLite 分块与 Chroma 向量索引的一致性。"""

    def __init__(
        self,
        session: AsyncSession,
        vector_store: ChromaVectorStore,
    ) -> None:
        """初始化审计器。"""
        self.session = session
        self.vector_store = vector_store

    async def audit(
        self,
        knowledge_base_id: int,
        batch_size: int = 500,
        collection_name: str | None = None,
    ) -> VectorIndexAuditReport:
        """审计指定知识库的 SQLite 与 Chroma 数据。"""
        if isinstance(knowledge_base_id, bool) or not isinstance(knowledge_base_id, int):
            raise TypeError("knowledge_base_id 必须是整数")
        if knowledge_base_id <= 0:
            raise ValueError("knowledge_base_id 必须大于 0")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int):
            raise TypeError("batch_size 必须是整数")
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")
        if collection_name is not None:
            if not isinstance(collection_name, str):
                raise TypeError("collection_name 必须是字符串")
            if not collection_name.strip():
                raise ValueError("collection_name 不能为空")

        knowledge_base = await KnowledgeBaseRepository(self.session).get_by_id(knowledge_base_id)

        sqlite_chunks = []
        if knowledge_base is not None:
            repository = DocumentChunkRepository(self.session)
            offset = 0

            while True:
                batch = await repository.get_by_knowledge_base(
                    knowledge_base_id,
                    offset=offset,
                    limit=batch_size,
                )
                sqlite_chunks.extend(batch)

                if len(batch) < batch_size:
                    break

                offset += len(batch)

        sqlite_by_id = {str(chunk.id): chunk for chunk in sqlite_chunks}

        collection_name = collection_name or f"knowledge_base_{knowledge_base_id}"
        collection_names = {
            getattr(item, "name", item) for item in self.vector_store.client.list_collections()
        }
        collection_exists = collection_name in collection_names

        records = (
            self.vector_store.get_all_records(
                collection_name,
                batch_size=batch_size,
            )
            if collection_exists
            else []
        )

        chroma_ids = set()
        invalid_metadata_ids = []

        for record in records:
            if not isinstance(record, dict):
                raise TypeError("Chroma 记录格式无效")

            vector_id = record.get("id")
            if not isinstance(vector_id, str) or not vector_id:
                raise ValueError("Chroma 返回了无效的向量 ID")

            chroma_ids.add(vector_id)

            chunk = sqlite_by_id.get(vector_id)
            metadata = record.get("metadata")

            if chunk is None or not isinstance(metadata, dict):
                invalid_metadata_ids.append(vector_id)
                continue

            expected_metadata = {
                "knowledge_base_id": knowledge_base_id,
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
            }

            if any(
                type(metadata.get(key)) is not int or metadata.get(key) != expected
                for key, expected in expected_metadata.items()
            ):
                invalid_metadata_ids.append(vector_id)

        sqlite_ids = set(sqlite_by_id)

        return VectorIndexAuditReport(
            knowledge_base_id=knowledge_base_id,
            knowledge_base_exists=knowledge_base is not None,
            collection_exists=collection_exists,
            sqlite_chunk_count=len(sqlite_ids),
            chroma_vector_count=len(records),
            missing_vector_ids=sorted(sqlite_ids - chroma_ids),
            orphan_vector_ids=sorted(chroma_ids - sqlite_ids),
            invalid_metadata_ids=sorted(set(invalid_metadata_ids)),
        )
