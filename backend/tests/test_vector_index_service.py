"""向量索引协调服务测试。"""

from unittest.mock import AsyncMock, Mock

import pytest

from app.models import DocumentChunk
from app.services.vector_index import VectorIndexService


@pytest.fixture
def chunks():
    """构造两条测试分块。"""
    return [
        DocumentChunk(
            id=1,
            document_id=10,
            chunk_index=0,
            content="第一段知识库测试文本",
            token_count=12,
            start_index=0,
            end_index=12,
        ),
        DocumentChunk(
            id=2,
            document_id=10,
            chunk_index=1,
            content="第二段知识库测试文本",
            token_count=15,
            start_index=12,
            end_index=27,
        ),
    ]


@pytest.fixture
def dependencies():
    """构造 Embedding 和向量存储模拟对象。"""
    embedding_service = Mock()
    embedding_service.embed_texts = AsyncMock(
        return_value=[
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]
    )

    vector_store = Mock()

    return embedding_service, vector_store


@pytest.fixture
def service(dependencies):
    """构造向量索引服务。"""
    return VectorIndexService(*dependencies)


@pytest.mark.asyncio
async def test_index_chunks_success(service, dependencies, chunks):
    """验证分块向量化和 ChromaDB 写入。"""
    embedding_service, vector_store = dependencies

    await service.index_chunks(chunks, knowledge_base_id=5)

    embedding_service.embed_texts.assert_awaited_once_with(
        ["第一段知识库测试文本", "第二段知识库测试文本"]
    )

    vector_store.upsert.assert_called_once_with(
        collection_name="knowledge_base_5",
        ids=["1", "2"],
        embeddings=[
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ],
        metadatas=[
            {
                "document_id": 10,
                "knowledge_base_id": 5,
                "chunk_index": 0,
                "token_count": 12,
                "start_index": 0,
                "end_index": 12,
            },
            {
                "document_id": 10,
                "knowledge_base_id": 5,
                "chunk_index": 1,
                "token_count": 15,
                "start_index": 12,
                "end_index": 27,
            },
        ],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chunks", "knowledge_base_id", "error"),
    [
        ([], 5, ValueError),
        ("invalid", 5, TypeError),
        ([object()], 5, TypeError),
        ([], 0, ValueError),
        ([], True, TypeError),
        ([], "5", TypeError),
    ],
)
async def test_index_chunks_rejects_invalid_inputs(
    service,
    dependencies,
    chunks,
    knowledge_base_id,
    error,
):
    """验证无效输入被拒绝，且不会调用外部服务。"""
    embedding_service, vector_store = dependencies

    with pytest.raises(error):
        await service.index_chunks(chunks, knowledge_base_id)

    embedding_service.embed_texts.assert_not_awaited()
    vector_store.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_index_chunks_rejects_duplicate_ids(service, dependencies, chunks):
    """验证重复分块 ID 被拒绝。"""
    embedding_service, vector_store = dependencies
    chunks[1].id = chunks[0].id

    with pytest.raises(ValueError, match="重复 ID"):
        await service.index_chunks(chunks, knowledge_base_id=5)

    embedding_service.embed_texts.assert_not_awaited()
    vector_store.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_index_chunks_rejects_empty_content(service, dependencies, chunks):
    """验证空分块文本被拒绝。"""
    embedding_service, vector_store = dependencies
    chunks[0].content = "   "

    with pytest.raises(ValueError, match="分块文本不能为空"):
        await service.index_chunks(chunks, knowledge_base_id=5)

    embedding_service.embed_texts.assert_not_awaited()
    vector_store.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_index_chunks_propagates_embedding_error(
    service,
    dependencies,
    chunks,
):
    """验证 Embedding 失败时异常向上传递。"""
    embedding_service, vector_store = dependencies
    embedding_service.embed_texts.side_effect = RuntimeError("Embedding 服务异常")

    with pytest.raises(RuntimeError, match="Embedding 服务异常"):
        await service.index_chunks(chunks, knowledge_base_id=5)

    vector_store.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_index_chunks_propagates_vector_store_error(
    service,
    dependencies,
    chunks,
):
    """验证 ChromaDB 写入失败时异常向上传递。"""
    embedding_service, vector_store = dependencies
    vector_store.upsert.side_effect = RuntimeError("ChromaDB 写入异常")

    with pytest.raises(RuntimeError, match="ChromaDB 写入异常"):
        await service.index_chunks(chunks, knowledge_base_id=5)

    embedding_service.embed_texts.assert_awaited_once()
    vector_store.upsert.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("embeddings", "error", "message"),
    [
        ([[0.1, 0.2]], ValueError, "数量必须与分块数量一致"),
        ([[], [0.1, 0.2]], ValueError, "必须是非空列表"),
        ([[0.1], [0.2, 0.3]], ValueError, "维度必须一致"),
        ([[0.1, "invalid"], [0.2, 0.3]], TypeError, "必须是数值"),
        ([[0.1, float("nan")], [0.2, 0.3]], ValueError, "有限数值"),
        ([[0.1, float("inf")], [0.2, 0.3]], ValueError, "有限数值"),
        ([[0.1, True], [0.2, 0.3]], TypeError, "必须是数值"),
        (None, TypeError, "必须是列表"),
    ],
)
async def test_index_chunks_rejects_invalid_embeddings(
    service,
    dependencies,
    chunks,
    embeddings,
    error,
    message,
):
    """验证异常 Embedding 响应不会写入 ChromaDB。"""
    embedding_service, vector_store = dependencies
    embedding_service.embed_texts.return_value = embeddings

    with pytest.raises(error, match=message):
        await service.index_chunks(chunks, knowledge_base_id=5)

    vector_store.upsert.assert_not_called()


@pytest.mark.asyncio
async def test_index_chunks_processes_multiple_batches(dependencies, chunks):
    """验证分块按照配置的批次大小依次写入。"""
    embedding_service, vector_store = dependencies
    embedding_service.embed_texts.side_effect = [
        [[0.1, 0.2]],
        [[0.3, 0.4]],
    ]

    service = VectorIndexService(
        embedding_service,
        vector_store,
        batch_size=1,
    )

    await service.index_chunks(chunks, knowledge_base_id=5)

    assert embedding_service.embed_texts.await_count == 2
    assert vector_store.upsert.call_count == 2

    calls = vector_store.upsert.call_args_list
    assert calls[0].kwargs["ids"] == ["1"]
    assert calls[1].kwargs["ids"] == ["2"]


@pytest.mark.parametrize(
    ("batch_size", "error"),
    [
        (0, ValueError),
        (-1, ValueError),
        (True, TypeError),
        (1.5, TypeError),
    ],
)
def test_rejects_invalid_batch_size(dependencies, batch_size, error):
    """验证批次大小必须是正整数。"""
    embedding_service, vector_store = dependencies

    with pytest.raises(error, match="batch_size"):
        VectorIndexService(
            embedding_service,
            vector_store,
            batch_size=batch_size,
        )


@pytest.mark.asyncio
async def test_index_chunks_preserves_previous_batch_on_failure(
    dependencies,
    chunks,
):
    """验证后续批次失败时保留已成功写入的批次。"""
    embedding_service, vector_store = dependencies
    embedding_service.embed_texts.side_effect = [
        [[0.1, 0.2]],
        RuntimeError("第二批 Embedding 失败"),
    ]

    service = VectorIndexService(
        embedding_service,
        vector_store,
        batch_size=1,
    )

    with pytest.raises(RuntimeError, match="第二批 Embedding 失败"):
        await service.index_chunks(chunks, knowledge_base_id=5)

    assert embedding_service.embed_texts.await_count == 2
    vector_store.upsert.assert_called_once()
    assert vector_store.upsert.call_args.kwargs["ids"] == ["1"]


@pytest.mark.asyncio
async def test_index_chunks_uses_custom_collection(dependencies, chunks):
    """验证可以指定临时向量集合。"""
    embedding_service, vector_store = dependencies

    service = VectorIndexService(
        embedding_service,
        vector_store,
        collection_name="knowledge_base_5_rebuild",
    )

    await service.index_chunks(chunks, knowledge_base_id=5)

    assert vector_store.upsert.call_args.kwargs["collection_name"] == "knowledge_base_5_rebuild"


@pytest.mark.parametrize(
    ("collection_name", "error"),
    [
        ("", ValueError),
        ("   ", ValueError),
        (123, TypeError),
    ],
)
def test_rejects_invalid_collection_name(
    dependencies,
    collection_name,
    error,
):
    """验证自定义集合名称必须有效。"""
    embedding_service, vector_store = dependencies

    with pytest.raises(error, match="collection_name"):
        VectorIndexService(
            embedding_service,
            vector_store,
            collection_name=collection_name,
        )
