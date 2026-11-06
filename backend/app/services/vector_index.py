"""KnowledgeFlow 向量索引协调服务。"""

import math

from app.embeddings import EmbeddingService
from app.models import DocumentChunk
from app.retrieval.text_builder import RetrievalTextBuilder
from app.vectorstore.chroma import ChromaVectorStore


class VectorIndexService:
    """协调文本向量化和 ChromaDB 向量持久化。"""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: ChromaVectorStore,
        batch_size: int = 32,
        collection_name: str | None = None,
    ) -> None:
        """初始化服务，允许指定向量集合名称。"""
        if isinstance(batch_size, bool) or not isinstance(batch_size, int):
            raise TypeError("batch_size 必须是整数")
        if batch_size <= 0:
            raise ValueError("batch_size 必须大于 0")

        if collection_name is not None:
            if not isinstance(collection_name, str):
                raise TypeError("collection_name 必须是字符串或 None")
            if not collection_name.strip():
                raise ValueError("collection_name 不能为空")

        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.batch_size = batch_size
        self.collection_name = collection_name

    @staticmethod
    def _validate_inputs(
        chunks: list[DocumentChunk],
        knowledge_base_id: int,
    ) -> None:
        """校验知识库 ID 和待索引分块。"""
        if isinstance(knowledge_base_id, bool) or not isinstance(knowledge_base_id, int):
            raise TypeError("knowledge_base_id 必须是整数")

        if knowledge_base_id <= 0:
            raise ValueError("knowledge_base_id 必须大于 0")

        if not isinstance(chunks, list):
            raise TypeError("chunks 必须是列表")

        if not chunks:
            raise ValueError("待索引分块不能为空")

        ids = []

        for chunk in chunks:
            if not isinstance(chunk, DocumentChunk):
                raise TypeError("chunks 中的元素必须是 DocumentChunk 类型")

            if isinstance(chunk.id, bool) or not isinstance(chunk.id, int):
                raise ValueError("分块必须具有有效的数据库 ID")

            if chunk.id <= 0:
                raise ValueError("分块 ID 必须大于 0")

            if not isinstance(chunk.content, str) or not chunk.content.strip():
                raise ValueError("分块文本不能为空")

            ids.append(chunk.id)

        if len(ids) != len(set(ids)):
            raise ValueError("待索引分块不能包含重复 ID")

    @staticmethod
    def _validate_embeddings(
        embeddings: list[list[float]],
        expected_count: int,
    ) -> None:
        """校验 Embedding 响应数量、维度和数值。"""
        if not isinstance(embeddings, list):
            raise TypeError("Embedding 响应必须是列表")

        if len(embeddings) != expected_count:
            raise ValueError("Embedding 数量必须与分块数量一致")

        dimension = None

        for embedding in embeddings:
            if not isinstance(embedding, list) or not embedding:
                raise ValueError("Embedding 必须是非空列表")

            if dimension is None:
                dimension = len(embedding)
            elif len(embedding) != dimension:
                raise ValueError("Embedding 向量维度必须一致")

            for value in embedding:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError("Embedding 元素必须是数值")

                if not math.isfinite(value):
                    raise ValueError("Embedding 元素必须是有限数值")

    async def index_chunks(
        self,
        chunks: list[DocumentChunk],
        knowledge_base_id: int,
    ) -> None:
        """分批生成分块向量并写入对应知识库集合。"""
        self._validate_inputs(chunks, knowledge_base_id)

        collection_name = self.collection_name or f"knowledge_base_{knowledge_base_id}"

        for start in range(0, len(chunks), self.batch_size):
            batch = chunks[start : start + self.batch_size]
            texts = [
                RetrievalTextBuilder.build(
                    chunk.content,
                    chunk.chunk_metadata,
                )
                for chunk in batch
            ]

            embeddings = await self.embedding_service.embed_texts(texts)
            self._validate_embeddings(embeddings, len(batch))

            ids = [str(chunk.id) for chunk in batch]
            metadatas = [
                {
                    "document_id": chunk.document_id,
                    "knowledge_base_id": knowledge_base_id,
                    "chunk_index": chunk.chunk_index,
                    "token_count": chunk.token_count,
                    "start_index": chunk.start_index,
                    "end_index": chunk.end_index,
                }
                for chunk in batch
            ]

            self.vector_store.upsert(
                collection_name=collection_name,
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
            )
