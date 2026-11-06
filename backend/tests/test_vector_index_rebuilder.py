"""临时向量索引重建服务测试。"""

from unittest.mock import AsyncMock, Mock

import pytest

from app.models import Document, DocumentChunk, KnowledgeBase
from app.reindex.rebuilder import VectorIndexRebuilder
from app.vectorstore.chroma import ChromaVectorStore


@pytest.fixture
def dependencies(tmp_path):
    """构造独立 Chroma、Embedding 模拟对象。"""
    embedding = Mock()
    embedding.embed_texts = AsyncMock(
        side_effect=lambda texts: [[float(index + 1), 0.2, 0.3] for index, _ in enumerate(texts)]
    )
    vector_store = ChromaVectorStore(tmp_path / "chroma")
    return embedding, vector_store


async def seed_database(session, chunk_count=5):
    """创建测试知识库及已完成文档。"""
    kb = KnowledgeBase(name="重建测试知识库")
    session.add(kb)
    await session.flush()

    document = Document(
        knowledge_base_id=kb.id,
        name="rebuild.txt",
        file_type="txt",
        file_path="uploads/rebuild.txt",
        file_size=100,
        content_hash="b" * 64,
        status="completed",
    )
    session.add(document)
    await session.flush()

    chunks = [
        DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=f"重建测试内容 {index}",
            token_count=10,
            start_index=index * 10,
            end_index=index * 10 + 10,
        )
        for index in range(chunk_count)
    ]
    session.add_all(chunks)
    await session.flush()

    return kb, document, chunks


@pytest.mark.asyncio
async def test_rebuild_processes_multiple_pages(database, dependencies):
    """验证分页读取、临时索引写入和最终审计。"""
    _, session_factory = database
    embedding, vector_store = dependencies

    async with session_factory() as session:
        kb, _, chunks = await seed_database(session)

        report = await VectorIndexRebuilder(
            session,
            embedding,
            vector_store,
        ).rebuild(
            kb.id,
            "knowledge_base_test_rebuild",
            page_size=2,
            index_batch_size=1,
        )

        assert report.knowledge_base_id == kb.id
        assert report.collection_name == "knowledge_base_test_rebuild"
        assert report.indexed_chunk_count == len(chunks)
        assert report.page_count == 3
        assert report.is_consistent is True
        assert report.audit_report.sqlite_chunk_count == 5
        assert report.audit_report.chroma_vector_count == 5
        assert embedding.embed_texts.await_count == 5

        records = vector_store.get_all_records(report.collection_name)
        assert {item["id"] for item in records} == {str(chunk.id) for chunk in chunks}


@pytest.mark.asyncio
async def test_rebuild_empty_knowledge_base(database, dependencies):
    """验证空知识库也能创建集合并通过审计。"""
    _, session_factory = database
    embedding, vector_store = dependencies

    async with session_factory() as session:
        kb, _, _ = await seed_database(session, chunk_count=0)

        report = await VectorIndexRebuilder(
            session,
            embedding,
            vector_store,
        ).rebuild(kb.id, "knowledge_base_empty_rebuild")

        assert report.indexed_chunk_count == 0
        assert report.page_count == 0
        assert report.is_consistent is True
        embedding.embed_texts.assert_not_awaited()


@pytest.mark.asyncio
async def test_rebuild_rejects_existing_collection(database, dependencies):
    """验证目标集合已存在时拒绝覆盖。"""
    _, session_factory = database
    embedding, vector_store = dependencies
    collection = vector_store.get_or_create_collection("knowledge_base_existing_rebuild")
    collection.upsert(
        ids=["old-vector"],
        embeddings=[[0.1, 0.2, 0.3]],
        metadatas=[{"source": "existing"}],
    )

    async with session_factory() as session:
        kb, _, _ = await seed_database(session)

        with pytest.raises(ValueError, match="拒绝覆盖"):
            await VectorIndexRebuilder(
                session,
                embedding,
                vector_store,
            ).rebuild(kb.id, "knowledge_base_existing_rebuild")

    embedding.embed_texts.assert_not_awaited()

    records = vector_store.get_all_records("knowledge_base_existing_rebuild")
    assert [item["id"] for item in records] == ["old-vector"]


@pytest.mark.asyncio
async def test_rebuild_rejects_missing_knowledge_base(database, dependencies):
    """验证不存在的知识库不会创建集合。"""
    _, session_factory = database
    embedding, vector_store = dependencies

    async with session_factory() as session:
        with pytest.raises(ValueError, match="知识库不存在"):
            await VectorIndexRebuilder(
                session,
                embedding,
                vector_store,
            ).rebuild(999, "knowledge_base_missing_rebuild")

    assert vector_store.client.list_collections() == []
    embedding.embed_texts.assert_not_awaited()


@pytest.mark.asyncio
async def test_rebuild_propagates_embedding_error(database, dependencies):
    """验证向量化失败时保留临时集合并传递异常。"""
    _, session_factory = database
    embedding, vector_store = dependencies
    embedding.embed_texts.side_effect = RuntimeError("Embedding 服务异常")

    async with session_factory() as session:
        kb, _, _ = await seed_database(session)

        with pytest.raises(RuntimeError, match="Embedding 服务异常"):
            await VectorIndexRebuilder(
                session,
                embedding,
                vector_store,
            ).rebuild(kb.id, "knowledge_base_failed_rebuild")

    names = {item.name for item in vector_store.client.list_collections()}
    assert "knowledge_base_failed_rebuild" not in names


@pytest.mark.asyncio
async def test_rebuild_returns_inconsistent_audit_report(database, dependencies):
    """验证审计不一致时返回报告而不是误报成功。"""
    _, session_factory = database
    embedding, vector_store = dependencies

    async with session_factory() as session:
        kb, _, _ = await seed_database(session)

        # 模拟索引写入成功后出现向量缺失。
        original_upsert = vector_store.upsert

        def upsert_without_last_vector(**kwargs):
            original_upsert(
                collection_name=kwargs["collection_name"],
                ids=kwargs["ids"][:-1],
                embeddings=kwargs["embeddings"][:-1],
                metadatas=kwargs["metadatas"][:-1],
            )

        vector_store.upsert = upsert_without_last_vector

        report = await VectorIndexRebuilder(
            session,
            embedding,
            vector_store,
        ).rebuild(
            kb.id,
            "knowledge_base_inconsistent_rebuild",
            page_size=10,
        )

        assert report.is_consistent is False
        assert report.audit_report.missing_vector_ids == ["5"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("knowledge_base_id", "collection_name", "page_size", "index_batch_size", "error"),
    [
        (True, "rebuild", 100, 32, TypeError),
        (0, "rebuild", 100, 32, ValueError),
        (1, "", 100, 32, ValueError),
        (1, 123, 100, 32, TypeError),
        (1, "rebuild", 0, 32, ValueError),
        (1, "rebuild", 100, False, TypeError),
    ],
)
async def test_rebuild_rejects_invalid_arguments(
    database,
    dependencies,
    knowledge_base_id,
    collection_name,
    page_size,
    index_batch_size,
    error,
):
    """验证重建参数无效时拒绝执行。"""
    _, session_factory = database
    embedding, vector_store = dependencies

    async with session_factory() as session:
        with pytest.raises(error):
            await VectorIndexRebuilder(
                session,
                embedding,
                vector_store,
            ).rebuild(
                knowledge_base_id,
                collection_name,
                page_size,
                index_batch_size,
            )

    assert vector_store.client.list_collections() == []
    embedding.embed_texts.assert_not_awaited()
