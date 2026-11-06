"""KnowledgeFlow Agent API 测试。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.executor import AgentResponse
from app.api.dependencies import get_agent_executor, get_rag_service
from app.api.routes.agent import router
from app.services.knowledge_base import KnowledgeBaseService


class FakeAgentExecutor:
    """模拟 Agent 执行器。"""

    def __init__(self, result=None, error=None):
        self.result = result or AgentResponse(
            answer="这是 Agent 回答。",
            tool_calls_count=1,
            iterations=1,
        )
        self.error = error
        self.called = False
        self.query = None

    async def run(self, query):
        self.called = True
        self.query = query
        if self.error is not None:
            raise self.error
        return self.result


class FakeRAGService:
    """提供知识库会话上下文。"""

    def __init__(self):
        self.hybrid_search_service = SimpleNamespace(session=object())


def create_client(monkeypatch, executor, knowledge_base_exists=True):
    """创建独立测试客户端。"""

    async def fake_get_by_id(self, knowledge_base_id):
        return object() if knowledge_base_exists else None

    monkeypatch.setattr(KnowledgeBaseService, "get_by_id", fake_get_by_id)

    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.dependency_overrides[get_rag_service] = FakeRAGService
    application.dependency_overrides[get_agent_executor] = lambda: executor

    return TestClient(application)


def test_agent_returns_answer_and_execution_stats(monkeypatch):
    """验证 Agent 回答及执行统计。"""
    executor = FakeAgentExecutor()
    client = create_client(monkeypatch, executor)

    response = client.post(
        "/api/v1/knowledge-bases/1/agent",
        json={"query": "  总结知识库  "},
    )

    assert response.status_code == 200
    assert response.json() == {
        "knowledge_base_id": 1,
        "query": "总结知识库",
        "answer": "这是 Agent 回答。",
        "tool_calls_count": 1,
        "iterations": 1,
    }
    assert executor.called is True
    assert executor.query == "总结知识库"


def test_agent_returns_not_found_for_missing_knowledge_base(monkeypatch):
    """验证知识库不存在时不执行 Agent。"""
    executor = FakeAgentExecutor()
    client = create_client(
        monkeypatch,
        executor,
        knowledge_base_exists=False,
    )

    response = client.post(
        "/api/v1/knowledge-bases/999/agent",
        json={"query": "测试"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "知识库不存在"
    assert executor.called is False


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "   "},
    ],
)
def test_agent_rejects_invalid_query(monkeypatch, payload):
    """验证空问题返回 422。"""
    executor = FakeAgentExecutor()
    client = create_client(monkeypatch, executor)

    response = client.post(
        "/api/v1/knowledge-bases/1/agent",
        json=payload,
    )

    assert response.status_code == 422
    assert executor.called is False


def test_agent_hides_internal_error(monkeypatch):
    """验证内部异常不会泄露给客户端。"""
    executor = FakeAgentExecutor(
        error=RuntimeError("内部模型连接信息"),
    )
    client = create_client(monkeypatch, executor)

    response = client.post(
        "/api/v1/knowledge-bases/1/agent",
        json={"query": "测试"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Agent 问答失败，请检查服务日志"
    assert "内部模型连接信息" not in response.text


def test_agent_route_is_registered_in_main_app():
    """验证正式应用注册 Agent 路由。"""
    from app.main import app

    path = "/api/v1/knowledge-bases/{knowledge_base_id}/agent"
    assert "post" in app.openapi()["paths"][path]
