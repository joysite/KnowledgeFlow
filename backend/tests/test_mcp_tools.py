"""KnowledgeFlow MCP 工具测试。"""

from types import SimpleNamespace

import pytest

import app.mcp_server.tools as tools_module
from app.mcp_server.tools import search_knowledge


class FakeSession:
    """模拟异步数据库会话。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class FakeRuntime:
    """模拟已经启动的 MCPRuntime。"""

    embedding_service = object()
    vector_store = object()

    def create_session(self):
        return FakeSession()


class FakeHybridSearchService:
    """模拟混合检索服务。"""

    def __init__(self, session, vector_search_service, bm25_search_service):
        self.session = session

    async def search(self, query, knowledge_base_id, top_k):
        return [
            SimpleNamespace(
                chunk_id=1,
                document_id=2,
                document_name="test.txt",
                chunk_index=0,
                content="KnowledgeFlow 使用 nomic-embed-text。",
                token_count=20,
                vector_distance=0.12,
                bm25_score=2.5,
                rrf_score=0.03,
            )
        ]


@pytest.mark.asyncio
async def test_search_knowledge_returns_serializable_results(monkeypatch):
    """验证 MCP 搜索工具返回结果和来源信息。"""
    monkeypatch.setattr(
        tools_module,
        "VectorSearchService",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        tools_module,
        "BM25SearchService",
        lambda session: object(),
    )
    monkeypatch.setattr(
        tools_module,
        "HybridSearchService",
        FakeHybridSearchService,
    )

    result = await search_knowledge(
        FakeRuntime(),
        knowledge_base_id=2,
        query="  使用什么向量模型？  ",
        top_k=3,
    )

    assert result["knowledge_base_id"] == 2
    assert result["query"] == "使用什么向量模型？"
    assert result["result_count"] == 1
    assert result["results"][0]["chunk_id"] == 1
    assert result["results"][0]["document_name"] == "test.txt"
    assert result["results"][0]["content"] == "KnowledgeFlow 使用 nomic-embed-text。"
    assert result["results"][0]["rrf_score"] == 0.03


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("knowledge_base_id", "query", "top_k", "error"),
    [
        (0, "测试", 5, ValueError),
        (True, "测试", 5, TypeError),
        (1, "", 5, ValueError),
        (1, "测试", 0, ValueError),
        (1, "测试", 101, ValueError),
        (1, "测试", True, TypeError),
    ],
)
async def test_search_knowledge_rejects_invalid_arguments(
    knowledge_base_id,
    query,
    top_k,
    error,
):
    """验证非法参数不会执行检索。"""
    with pytest.raises(error):
        await search_knowledge(
            FakeRuntime(),
            knowledge_base_id=knowledge_base_id,
            query=query,
            top_k=top_k,
        )


@pytest.mark.asyncio
async def test_search_knowledge_rejects_uninitialized_runtime():
    """验证运行资源未初始化时拒绝检索。"""
    runtime = FakeRuntime()
    runtime.embedding_service = None

    with pytest.raises(RuntimeError, match="尚未初始化"):
        await search_knowledge(runtime, 1, "测试")


@pytest.mark.asyncio
async def test_search_knowledge_returns_empty_results(monkeypatch):
    """验证没有匹配内容时返回空结果。"""

    class EmptyHybridSearchService:
        def __init__(self, *args, **kwargs):
            pass

        async def search(self, **kwargs):
            return []

    monkeypatch.setattr(
        tools_module,
        "VectorSearchService",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        tools_module,
        "BM25SearchService",
        lambda session: object(),
    )
    monkeypatch.setattr(
        tools_module,
        "HybridSearchService",
        EmptyHybridSearchService,
    )

    result = await search_knowledge(FakeRuntime(), 2, "不存在")

    assert result["result_count"] == 0
    assert result["results"] == []
