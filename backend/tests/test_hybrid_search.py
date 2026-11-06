"""KnowledgeFlow 混合检索服务测试。"""

from types import SimpleNamespace

import pytest

from app.services.hybrid_search import HybridSearchService


class FakeVectorSearchService:
    """模拟向量检索服务。"""

    def __init__(self, results):
        self.results = results
        self.called = False
        self.arguments = None

    async def search(self, query, knowledge_base_id, top_k):
        self.called = True
        self.arguments = (query, knowledge_base_id, top_k)
        return self.results


class FakeBM25SearchService:
    """模拟 BM25 检索服务。"""

    def __init__(self, results):
        self.results = results
        self.called = False
        self.arguments = None

    async def search(self, query, knowledge_base_id, top_k):
        self.called = True
        self.arguments = (query, knowledge_base_id, top_k)
        return self.results


def make_result(chunk_id, distance=None, score=None):
    """创建检索结果模拟对象。"""
    return SimpleNamespace(
        chunk_id=chunk_id,
        document_id=chunk_id + 100,
        document_name=f"文档{chunk_id}.txt",
        chunk_index=chunk_id % 10,
        content=f"分块内容 {chunk_id}",
        token_count=20,
        distance=distance,
        score=score,
    )


@pytest.mark.asyncio
async def test_search_fuses_vector_and_bm25_results():
    """验证双路召回结果能够正确融合。"""
    vector = FakeVectorSearchService(
        [
            make_result(1, distance=0.1),
            make_result(2, distance=0.2),
        ]
    )
    bm25 = FakeBM25SearchService(
        [
            make_result(2, score=3.5),
            make_result(3, score=2.5),
        ]
    )
    service = HybridSearchService(object(), vector, bm25)

    results = await service.search("Python 检索", 1, top_k=3)

    assert [item.chunk_id for item in results] == [2, 1, 3]
    assert results[0].vector_distance == 0.2
    assert results[0].bm25_score == 3.5
    assert results[0].rrf_score == pytest.approx(1 / 62 + 1 / 61)

    assert results[1].vector_distance == 0.1
    assert results[1].bm25_score is None

    assert results[2].vector_distance is None
    assert results[2].bm25_score == 2.5

    assert results[0].content == "分块内容 2"
    assert results[0].document_name == "文档2.txt"


@pytest.mark.asyncio
async def test_search_passes_expanded_candidate_top_k():
    """验证两路召回使用扩展后的候选数量。"""
    vector = FakeVectorSearchService([])
    bm25 = FakeBM25SearchService([])
    service = HybridSearchService(object(), vector, bm25)

    await service.search("测试", 7, top_k=5)

    assert vector.arguments == ("测试", 7, 10)
    assert bm25.arguments == ("测试", 7, 10)


@pytest.mark.asyncio
async def test_search_returns_empty_when_both_retrievers_return_empty():
    """验证两路均无结果时返回空列表。"""
    vector = FakeVectorSearchService([])
    bm25 = FakeBM25SearchService([])
    service = HybridSearchService(object(), vector, bm25)

    assert await service.search("不存在", 1) == []


@pytest.mark.asyncio
async def test_search_supports_single_retriever_results():
    """验证单路召回结果仍能参与融合。"""
    vector = FakeVectorSearchService([make_result(1, distance=0.15)])
    bm25 = FakeBM25SearchService([])
    service = HybridSearchService(object(), vector, bm25)

    results = await service.search("向量检索", 1)

    assert len(results) == 1
    assert results[0].chunk_id == 1
    assert results[0].vector_distance == 0.15
    assert results[0].bm25_score is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "knowledge_base_id", "top_k", "error"),
    [
        ("", 1, 5, ValueError),
        ("   ", 1, 5, ValueError),
        ("测试", 0, 5, ValueError),
        ("测试", True, 5, TypeError),
        ("测试", 1, 0, ValueError),
        ("测试", 1, True, TypeError),
    ],
)
async def test_search_rejects_invalid_inputs(
    query,
    knowledge_base_id,
    top_k,
    error,
):
    """验证非法参数不会触发底层检索。"""
    vector = FakeVectorSearchService([])
    bm25 = FakeBM25SearchService([])
    service = HybridSearchService(object(), vector, bm25)

    with pytest.raises(error):
        await service.search(query, knowledge_base_id, top_k)

    assert vector.called is False
    assert bm25.called is False


@pytest.mark.asyncio
async def test_search_propagates_retriever_errors():
    """验证底层检索异常向上抛出，不静默降级。"""
    vector = FakeVectorSearchService([])
    bm25 = FakeBM25SearchService([])
    vector.search = failing_search

    service = HybridSearchService(object(), vector, bm25)

    with pytest.raises(RuntimeError, match="向量检索失败"):
        await service.search("测试", 1)

    assert bm25.called is False


async def failing_search(query, knowledge_base_id, top_k):
    """模拟向量检索失败。"""
    raise RuntimeError("向量检索失败")
