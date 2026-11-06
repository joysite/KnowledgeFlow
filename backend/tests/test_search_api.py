"""KnowledgeFlow 知识库检索 API 测试。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_hybrid_search_service
from app.api.routes.search import router
from app.services.knowledge_base import KnowledgeBaseService


class FakeHybridSearchService:
    """隔离真实向量服务的模拟检索服务。"""

    def __init__(self, results=None, error=None):
        self.session = object()
        self.results = results or []
        self.error = error
        self.called = False
        self.arguments = None

    async def search(self, query, knowledge_base_id, top_k):
        self.called = True
        self.arguments = {
            "query": query,
            "knowledge_base_id": knowledge_base_id,
            "top_k": top_k,
        }
        if self.error is not None:
            raise self.error
        return self.results


def create_client(monkeypatch, service, knowledge_base_exists=True):
    """创建独立测试客户端。"""

    async def fake_get_by_id(self, knowledge_base_id):
        return object() if knowledge_base_exists else None

    monkeypatch.setattr(KnowledgeBaseService, "get_by_id", fake_get_by_id)

    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.dependency_overrides[get_hybrid_search_service] = lambda: service

    return TestClient(application)


def test_search_returns_results(monkeypatch):
    """测试检索成功并返回分块内容。"""
    service = FakeHybridSearchService(
        results=[
            SimpleNamespace(
                chunk_id=12,
                document_id=3,
                document_name="技术文档.pdf",
                chunk_index=2,
                content="这是检索到的原文内容",
                token_count=128,
                vector_distance=0.15,
                bm25_score=2.5,
                rrf_score=0.0325,
            )
        ]
    )
    client = create_client(monkeypatch, service)

    response = client.post(
        "/api/v1/knowledge-bases/1/search",
        json={"query": "  向量检索  ", "top_k": 5},
    )

    assert response.status_code == 200
    assert response.json() == {
        "knowledge_base_id": 1,
        "query": "向量检索",
        "results": [
            {
                "chunk_id": 12,
                "document_id": 3,
                "document_name": "技术文档.pdf",
                "chunk_index": 2,
                "content": "这是检索到的原文内容",
                "token_count": 128,
                "vector_distance": 0.15,
                "bm25_score": 2.5,
                "rrf_score": 0.0325,
            }
        ],
    }
    assert service.arguments == {
        "query": "向量检索",
        "knowledge_base_id": 1,
        "top_k": 5,
    }


def test_search_returns_empty_results(monkeypatch):
    """测试没有召回结果时返回空列表。"""
    service = FakeHybridSearchService()
    client = create_client(monkeypatch, service)

    response = client.post(
        "/api/v1/knowledge-bases/1/search",
        json={"query": "不存在的内容"},
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert service.called is True


def test_search_returns_not_found_for_missing_knowledge_base(monkeypatch):
    """测试知识库不存在时返回 404。"""
    service = FakeHybridSearchService()
    client = create_client(
        monkeypatch,
        service,
        knowledge_base_exists=False,
    )

    response = client.post(
        "/api/v1/knowledge-bases/999/search",
        json={"query": "测试查询"},
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
def test_search_rejects_invalid_request(monkeypatch, payload):
    """测试非法查询参数返回 422。"""
    service = FakeHybridSearchService()
    client = create_client(monkeypatch, service)

    response = client.post(
        "/api/v1/knowledge-bases/1/search",
        json=payload,
    )

    assert response.status_code == 422
    assert service.called is False


def test_search_hides_internal_error(monkeypatch):
    """测试检索内部异常不会泄露实现细节。"""
    service = FakeHybridSearchService(error=RuntimeError("内部向量数据库连接信息"))
    client = create_client(monkeypatch, service)

    response = client.post(
        "/api/v1/knowledge-bases/1/search",
        json={"query": "测试查询"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "知识库检索失败，请检查服务日志"
    assert "内部向量数据库连接信息" not in response.text


def test_search_route_is_registered_in_main_app():
    """测试正式应用已注册检索路由。"""
    from app.main import app

    path = "/api/v1/knowledge-bases/{knowledge_base_id}/search"
    assert "post" in app.openapi()["paths"][path]
