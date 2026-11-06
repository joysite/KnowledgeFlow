"""KnowledgeFlow RAG API 测试。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_rag_service
from app.api.routes.rag import router
from app.services.context_builder import ContextSource
from app.services.knowledge_base import KnowledgeBaseService
from app.services.rag import RAGResponse


class FakeRAGService:
    """模拟 RAG 服务。"""

    def __init__(self, result=None, error=None):
        self.hybrid_search_service = SimpleNamespace(session=object())
        self.result = result
        self.error = error
        self.called = False
        self.arguments = None

    async def answer(self, query, knowledge_base_id, top_k):
        self.called = True
        self.arguments = {
            "query": query,
            "knowledge_base_id": knowledge_base_id,
            "top_k": top_k,
        }
        if self.error is not None:
            raise self.error
        return self.result


def make_response():
    """创建模拟 RAG 响应。"""
    return RAGResponse(
        query="知识库检索",
        answer="这是基于知识库的回答 [1]。",
        sources=[
            ContextSource(
                source_id=1,
                chunk_id=12,
                document_id=3,
                document_name="技术文档.pdf",
                chunk_index=2,
                content="这是检索到的原文内容",
                rrf_score=0.0325,
            )
        ],
        retrieved_count=2,
        context_token_count=128,
    )


def create_client(monkeypatch, service, knowledge_base_exists=True):
    """创建独立测试客户端。"""

    async def fake_get_by_id(self, knowledge_base_id):
        return object() if knowledge_base_exists else None

    monkeypatch.setattr(KnowledgeBaseService, "get_by_id", fake_get_by_id)

    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.dependency_overrides[get_rag_service] = lambda: service

    return TestClient(application)


def test_rag_returns_answer_and_sources(monkeypatch):
    """测试问答成功并返回完整来源信息。"""
    service = FakeRAGService(result=make_response())
    client = create_client(monkeypatch, service)

    response = client.post(
        "/api/v1/knowledge-bases/1/rag",
        json={"query": "  知识库检索  ", "top_k": 5},
    )

    assert response.status_code == 200
    assert response.json() == {
        "knowledge_base_id": 1,
        "query": "知识库检索",
        "answer": "这是基于知识库的回答 [1]。",
        "sources": [
            {
                "source_id": 1,
                "chunk_id": 12,
                "document_id": 3,
                "document_name": "技术文档.pdf",
                "chunk_index": 2,
                "content": "这是检索到的原文内容",
                "rrf_score": 0.0325,
            }
        ],
        "retrieved_count": 2,
        "context_token_count": 128,
    }
    assert service.arguments == {
        "query": "知识库检索",
        "knowledge_base_id": 1,
        "top_k": 5,
    }


def test_rag_returns_empty_sources(monkeypatch):
    """测试无检索结果时正常返回无来源回答。"""
    service = FakeRAGService(
        result=RAGResponse(
            query="不存在的问题",
            answer="知识库中没有相关内容。",
            sources=[],
            retrieved_count=0,
            context_token_count=0,
        )
    )
    client = create_client(monkeypatch, service)

    response = client.post(
        "/api/v1/knowledge-bases/1/rag",
        json={"query": "不存在的问题"},
    )

    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert response.json()["retrieved_count"] == 0


def test_rag_returns_not_found_for_missing_knowledge_base(monkeypatch):
    """测试知识库不存在时返回 404。"""
    service = FakeRAGService(result=make_response())
    client = create_client(
        monkeypatch,
        service,
        knowledge_base_exists=False,
    )

    response = client.post(
        "/api/v1/knowledge-bases/999/rag",
        json={"query": "测试问题"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "知识库不存在"
    assert service.called is False


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "测试", "top_k": 0},
        {"query": "测试", "top_k": 101},
        {"query": "测试", "top_k": True},
    ],
)
def test_rag_rejects_invalid_request(monkeypatch, payload):
    """测试非法请求参数返回 422。"""
    service = FakeRAGService(result=make_response())
    client = create_client(monkeypatch, service)

    response = client.post(
        "/api/v1/knowledge-bases/1/rag",
        json=payload,
    )

    assert response.status_code == 422
    assert service.called is False


def test_rag_hides_internal_error(monkeypatch):
    """测试内部异常不会泄露给客户端。"""
    service = FakeRAGService(error=RuntimeError("内部模型地址和连接信息"))
    client = create_client(monkeypatch, service)

    response = client.post(
        "/api/v1/knowledge-bases/1/rag",
        json={"query": "测试问题"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "知识库问答失败，请检查服务日志"
    assert "内部模型地址和连接信息" not in response.text


def test_rag_route_is_registered_in_main_app():
    """测试正式应用已注册 RAG 路由。"""
    from app.main import app

    path = "/api/v1/knowledge-bases/{knowledge_base_id}/rag"
    assert "post" in app.openapi()["paths"][path]
