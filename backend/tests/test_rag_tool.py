"""KnowledgeFlow RAG Agent 工具测试。"""

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from app.agent import (
    RAGToolArguments,
    ToolArgumentError,
    ToolRegistry,
    create_rag_tool,
)


@dataclass
class FakeSource:
    source_id: int = 1
    chunk_id: int = 10
    document_id: int = 2
    document_name: str = "测试文档"
    chunk_index: int = 0
    content: str = "知识库测试内容"
    rrf_score: float = 0.8


@dataclass
class FakeRAGResponse:
    query: str
    answer: str
    sources: list
    retrieved_count: int
    context_token_count: int


class FakeRAGService:
    """模拟现有 RAGService。"""

    def __init__(self):
        self.calls = []

    async def answer(self, query, knowledge_base_id, top_k=5):
        self.calls.append((query, knowledge_base_id, top_k))
        return FakeRAGResponse(
            query=query,
            answer="这是知识库回答。",
            sources=[FakeSource()],
            retrieved_count=3,
            context_token_count=120,
        )


def test_rag_tool_arguments_defaults():
    arguments = RAGToolArguments(
        query="测试问题",
        knowledge_base_id=1,
    )

    assert arguments.top_k == 5


@pytest.mark.parametrize(
    "payload",
    [
        {"query": "   ", "knowledge_base_id": 1},
        {"query": "测试", "knowledge_base_id": 0},
        {"query": "测试", "knowledge_base_id": True},
        {"query": "测试", "knowledge_base_id": 1, "top_k": 0},
        {"query": "测试", "knowledge_base_id": 1, "top_k": 101},
        {"query": "测试", "knowledge_base_id": 1, "unexpected": 1},
    ],
)
def test_rag_tool_arguments_reject_invalid_input(payload):
    with pytest.raises(ValidationError):
        RAGToolArguments.model_validate(payload)


@pytest.mark.asyncio
async def test_rag_tool_calls_existing_rag_service():
    rag_service = FakeRAGService()
    registry = ToolRegistry()
    registry.register(create_rag_tool(rag_service))

    result = await registry.call(
        "knowledge_rag",
        {
            "query": "  如何使用混合检索？  ",
            "knowledge_base_id": 1,
            "top_k": 3,
        },
    )

    assert rag_service.calls == [("如何使用混合检索？", 1, 3)]
    assert result["answer"] == "这是知识库回答。"
    assert result["retrieved_count"] == 3
    assert result["context_token_count"] == 120
    assert result["sources"][0]["document_name"] == "测试文档"


@pytest.mark.asyncio
async def test_rag_tool_uses_default_top_k():
    rag_service = FakeRAGService()
    registry = ToolRegistry()
    registry.register(create_rag_tool(rag_service))

    await registry.call(
        "knowledge_rag",
        {"query": "测试", "knowledge_base_id": 2},
    )

    assert rag_service.calls == [("测试", 2, 5)]


@pytest.mark.asyncio
async def test_rag_tool_rejects_invalid_arguments():
    registry = ToolRegistry()
    registry.register(create_rag_tool(FakeRAGService()))

    with pytest.raises(ToolArgumentError):
        await registry.call(
            "knowledge_rag",
            {"query": "测试", "knowledge_base_id": -1},
        )


def test_rag_tool_exports_ollama_schema():
    registry = ToolRegistry()
    registry.register(create_rag_tool(FakeRAGService()))

    tools = registry.to_ollama_tools()

    assert len(tools) == 1
    function = tools[0]["function"]
    assert function["name"] == "knowledge_rag"
    assert "query" in function["parameters"]["properties"]
    assert "knowledge_base_id" in function["parameters"]["properties"]
    assert "top_k" in function["parameters"]["properties"]
