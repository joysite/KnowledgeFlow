"""向量检索服务测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.vector_search import VectorSearchService


@pytest.fixture
def dependencies(monkeypatch):
    """构造检索服务依赖。"""
    embedding = Mock()
    embedding.embed_text = AsyncMock(return_value=[0.1, 0.2, 0.3])

    vector_store = Mock()
    vector_store.query.return_value = {
        "ids": [["2", "1", "3"]],
        "distances": [[0.05, 0.1, 0.2]],
    }

    repository = Mock()
    repository.get_by_ids = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=1,
                document_id=10,
                document=SimpleNamespace(name="测试文档.pdf"),
                chunk_index=0,
                content="第一段内容",
                token_count=12,
            ),
            SimpleNamespace(
                id=2,
                document_id=10,
                document=SimpleNamespace(name="测试文档.pdf"),
                chunk_index=1,
                content="第二段内容",
                token_count=15,
            ),
        ]
    )

    repository_class = Mock(return_value=repository)
    monkeypatch.setattr(
        "app.services.vector_search.DocumentChunkRepository",
        repository_class,
    )

    service = VectorSearchService(
        session=Mock(),
        embedding_service=embedding,
        vector_store=vector_store,
    )

    return service, embedding, vector_store, repository


@pytest.mark.asyncio
async def test_search_returns_results_in_vector_order(dependencies):
    """验证回查结果保持 Chroma 相似度顺序。"""
    service, embedding, vector_store, repository = dependencies

    results = await service.search("测试问题", knowledge_base_id=5, top_k=3)

    embedding.embed_text.assert_awaited_once_with("测试问题")
    vector_store.query.assert_called_once_with(
        collection_name="knowledge_base_5",
        query_embeddings=[[0.1, 0.2, 0.3]],
        n_results=3,
        where={"knowledge_base_id": 5},
    )
    repository.get_by_ids.assert_awaited_once_with(
        knowledge_base_id=5,
        chunk_ids=[2, 1, 3],
    )

    assert [item.chunk_id for item in results] == [2, 1]
    assert [item.distance for item in results] == pytest.approx([0.05, 0.1])
    assert results[0].content == "第二段内容"
    assert results[0].document_name == "测试文档.pdf"


@pytest.mark.asyncio
async def test_search_returns_empty_when_chroma_has_no_results(dependencies):
    """验证 Chroma 没有召回结果时直接返回空列表。"""
    service, embedding, vector_store, repository = dependencies
    vector_store.query.return_value = {
        "ids": [[]],
        "distances": [[]],
    }

    results = await service.search("不存在的内容", 5)

    assert results == []
    repository.get_by_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_skips_chunks_missing_from_sqlite(dependencies):
    """验证已经从 SQLite 删除的分块不会出现在结果中。"""
    service, _, vector_store, repository = dependencies
    repository.get_by_ids.return_value = []

    results = await service.search("测试问题", 5)

    assert results == []


@pytest.mark.asyncio
async def test_search_skips_invalid_chroma_ids_and_distances(dependencies):
    """验证无效向量 ID 和距离不会传入 SQLite。"""
    service, _, vector_store, repository = dependencies
    vector_store.query.return_value = {
        "ids": [["invalid", "0", "2", "3"]],
        "distances": [[0.01, 0.02, 0.03, "invalid"]],
    }

    results = await service.search("测试问题", 5)

    repository.get_by_ids.assert_awaited_once_with(
        knowledge_base_id=5,
        chunk_ids=[2],
    )
    assert [item.chunk_id for item in results] == [2]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "knowledge_base_id", "top_k", "error"),
    [
        ("", 5, 5, ValueError),
        ("   ", 5, 5, ValueError),
        ("问题", 0, 5, ValueError),
        ("问题", True, 5, TypeError),
        ("问题", "5", 5, TypeError),
        ("问题", 5, 0, ValueError),
        ("问题", 5, True, TypeError),
    ],
)
async def test_search_rejects_invalid_inputs(
    dependencies,
    query,
    knowledge_base_id,
    top_k,
    error,
):
    """验证非法检索参数不会触发外部服务。"""
    service, embedding, vector_store, repository = dependencies

    with pytest.raises(error):
        await service.search(query, knowledge_base_id, top_k)

    embedding.embed_text.assert_not_awaited()
    vector_store.query.assert_not_called()
    repository.get_by_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_propagates_embedding_error(dependencies):
    """验证 Embedding 异常向上传递。"""
    service, embedding, vector_store, repository = dependencies
    embedding.embed_text.side_effect = RuntimeError("Embedding 异常")

    with pytest.raises(RuntimeError, match="Embedding 异常"):
        await service.search("测试问题", 5)

    vector_store.query.assert_not_called()
    repository.get_by_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_propagates_vector_store_error(dependencies):
    """验证 Chroma 异常向上传递。"""
    service, _, vector_store, repository = dependencies
    vector_store.query.side_effect = RuntimeError("Chroma 异常")

    with pytest.raises(RuntimeError, match="Chroma 异常"):
        await service.search("测试问题", 5)

    repository.get_by_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_propagates_repository_error(dependencies):
    """验证 SQLite 回查异常向上传递。"""
    service, _, _, repository = dependencies
    repository.get_by_ids.side_effect = RuntimeError("数据库异常")

    with pytest.raises(RuntimeError, match="数据库异常"):
        await service.search("测试问题", 5)


@pytest.mark.asyncio
async def test_search_handles_missing_distance_list(dependencies):
    """验证距离结果缺失时不返回无法评分的候选。"""
    service, _, vector_store, repository = dependencies
    vector_store.query.return_value = {
        "ids": [["1"]],
        "distances": [],
    }

    results = await service.search("测试问题", 5)

    assert results == []
    repository.get_by_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_uses_custom_collection_name(dependencies):
    """验证指定集合名称时使用自定义 Chroma 集合。"""
    service, _, vector_store, _ = dependencies
    service.collection_name = "knowledge_base_2_rebuild"

    await service.search("测试问题", knowledge_base_id=2, top_k=3)

    assert vector_store.query.call_args.kwargs["collection_name"] == ("knowledge_base_2_rebuild")


@pytest.mark.asyncio
async def test_search_defaults_to_knowledge_base_collection(dependencies):
    """验证不指定集合名称时仍使用知识库默认集合。"""
    service, _, vector_store, _ = dependencies

    await service.search("测试问题", knowledge_base_id=2, top_k=3)

    assert vector_store.query.call_args.kwargs["collection_name"] == ("knowledge_base_2")
