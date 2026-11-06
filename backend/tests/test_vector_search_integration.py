"""KnowledgeFlow 真实 Ollama + Chroma + SQLite 检索集成测试。"""

import hashlib
import os
from pathlib import Path

import httpx
import pytest

from app.embeddings import EmbeddingService
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.services.vector_index import VectorIndexService
from app.services.vector_search import VectorSearchService
from app.vectorstore.chroma import ChromaVectorStore


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("KLF_RUN_LIVE_INTEGRATION") != "1",
    reason="设置 KLF_RUN_LIVE_INTEGRATION=1 后运行真实 Ollama 集成测试",
)
async def test_real_ollama_chroma_sqlite_vector_search(
    database,
    tmp_path: Path,
) -> None:
    """验证真实文本向量化、Chroma 检索和 SQLite 原文回查。"""
    _, session_factory = database

    content = (
        "KnowledgeFlow 使用 Ollama 的 nomic-embed-text 模型生成文本向量，"
        "向量维度为 768。ChromaDB 负责持久化存储向量，"
        "SQLite 保存文档分块原文和业务元数据。"
    )

    async with session_factory() as session:
        knowledge_base = KnowledgeBase(
            name="真实检索集成测试",
            description="临时测试知识库",
        )
        session.add(knowledge_base)
        await session.flush()

        document = Document(
            knowledge_base_id=knowledge_base.id,
            name="检索架构说明.txt",
            file_type="txt",
            file_path=str(tmp_path / "检索架构说明.txt"),
            file_size=len(content.encode("utf-8")),
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            status="completed",
        )
        session.add(document)
        await session.flush()

        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            content=content,
            token_count=40,
            start_index=0,
            end_index=len(content),
        )
        session.add(chunk)
        await session.commit()
        await session.refresh(chunk)

        vector_store = ChromaVectorStore(tmp_path / "chroma")
        async with httpx.AsyncClient() as client:
            embedding_service = EmbeddingService(client)
            index_service = VectorIndexService(
                embedding_service=embedding_service,
                vector_store=vector_store,
            )
            search_service = VectorSearchService(
                session=session,
                embedding_service=embedding_service,
                vector_store=vector_store,
            )

            # 真实调用 Ollama，为 SQLite 中的分块生成向量并写入 Chroma。
            await index_service.index_chunks([chunk], knowledge_base.id)

            # 真实调用 Ollama 将查询转换为向量，再由 Chroma 召回。
            results = await search_service.search(
                query="KnowledgeFlow 使用什么模型生成文本向量？",
                knowledge_base_id=knowledge_base.id,
                top_k=5,
            )

        assert len(results) == 1
        assert results[0].chunk_id == chunk.id
        assert results[0].document_id == document.id
        assert results[0].document_name == "检索架构说明.txt"
        assert results[0].content == content
        assert results[0].token_count == 40
        assert isinstance(results[0].distance, float)
        assert results[0].distance >= 0
