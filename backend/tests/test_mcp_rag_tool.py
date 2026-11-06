"""KnowledgeFlow MCP RAG 工具测试。"""

from types import SimpleNamespace

import pytest

import app.mcp_server.rag_tool as rag_tool
from app.mcp_server.rag_tool import answer_knowledge


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class FakeRuntime:
    embedding_service = object()
    vector_store = object()
    chat_service = object()

    def create_session(self):
        return FakeSession()


class FakeRAGService:
    def __init__(self, **kwargs):
        pass

    async def answer(self, query, knowledge_base_id, top_k):
        return SimpleNamespace(
            query=query,
            answer="KnowledgeFlow 使用 nomic-embed-text。[1]",
            retrieved_count=1,
            context_token_count=100,
            sources=[
                SimpleNamespace(
                    source_id=1,
                    chunk_id=1,
                    document_id=1,
                    document_name="knowledgeflow-agent-test.txt",
                    chunk_index=0,
                    content="向量模型：nomic-embed-text。",
                    rrf_score=0.03,
                )
            ],
        )


@pytest.mark.asyncio
async def test_answer_knowledge_returns_answer_and_sources(monkeypatch):
    """验证 RAG 结果及来源序列化。"""
    monkeypatch.setattr(
        rag_tool,
        "VectorSearchService",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        rag_tool,
        "BM25SearchService",
        lambda session: object(),
    )
    monkeypatch.setattr(
        rag_tool,
        "HybridSearchService",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(rag_tool, "RAGService", FakeRAGService)

    result = await answer_knowledge(
        FakeRuntime(),
        knowledge_base_id=2,
        query="  使用什么向量模型？  ",
        top_k=5,
    )

    assert result["knowledge_base_id"] == 2
    assert result["query"] == "使用什么向量模型？"
    assert result["answer"] == "KnowledgeFlow 使用 nomic-embed-text。[1]"
    assert result["retrieved_count"] == 1
    assert result["context_token_count"] == 100
    assert result["sources"][0]["source_id"] == 1
    assert result["sources"][0]["document_name"] == "knowledgeflow-agent-test.txt"


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
async def test_answer_knowledge_rejects_invalid_arguments(
    knowledge_base_id,
    query,
    top_k,
    error,
):
    """验证 RAG 工具参数校验。"""
    with pytest.raises(error):
        await answer_knowledge(
            FakeRuntime(),
            knowledge_base_id,
            query,
            top_k,
        )


@pytest.mark.asyncio
async def test_answer_knowledge_rejects_uninitialized_runtime():
    """验证 RAG 运行资源未初始化时拒绝执行。"""
    runtime = FakeRuntime()
    runtime.chat_service = None

    with pytest.raises(RuntimeError, match="尚未初始化"):
        await answer_knowledge(runtime, 2, "测试")
