"""KnowledgeFlow 知识库管理 API 测试。"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.session import get_db_session
from app.main import app
from app.services.knowledge_base import KnowledgeBaseService


def make_knowledge_base(
    knowledge_base_id: int = 1,
    name: str = "测试知识库",
) -> SimpleNamespace:
    """构造知识库响应对象。"""
    now = datetime.now(UTC).replace(tzinfo=None)
    return SimpleNamespace(
        id=knowledge_base_id,
        name=name,
        description="测试描述",
        created_at=now,
        updated_at=now,
    )


def create_client():
    """创建隔离数据库依赖的测试客户端。"""
    application = FastAPI()
    from app.api.routes.knowledge_bases import router

    application.include_router(router, prefix="/api/v1")

    async def fake_session():
        yield object()

    application.dependency_overrides[get_db_session] = fake_session
    return TestClient(application)


def test_create_knowledge_base(monkeypatch):
    """测试创建知识库并规范化名称。"""
    captured = {}

    async def fake_create(self, name, description=None):
        captured["name"] = name
        captured["description"] = description
        return make_knowledge_base(name=name)

    monkeypatch.setattr(KnowledgeBaseService, "create", fake_create)

    with create_client() as client:
        response = client.post(
            "/api/v1/knowledge-bases",
            json={"name": "  Python 知识库  ", "description": "学习资料"},
        )

    assert response.status_code == 201
    assert response.json()["name"] == "Python 知识库"
    assert captured == {
        "name": "Python 知识库",
        "description": "学习资料",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "a" * 129},
        {"name": "有效名称", "description": 123},
    ],
)
def test_create_rejects_invalid_payload(payload):
    """测试创建接口拒绝非法请求。"""
    with create_client() as client:
        response = client.post("/api/v1/knowledge-bases", json=payload)

    assert response.status_code == 422


def test_list_knowledge_bases(monkeypatch):
    """测试知识库分页查询。"""
    captured = {}

    async def fake_list_all(self, offset=0, limit=20):
        captured.update(offset=offset, limit=limit)
        return [
            make_knowledge_base(2, "知识库二"),
            make_knowledge_base(3, "知识库三"),
        ]

    monkeypatch.setattr(KnowledgeBaseService, "list_all", fake_list_all)

    with create_client() as client:
        response = client.get(
            "/api/v1/knowledge-bases",
            params={"offset": 1, "limit": 2},
        )

    assert response.status_code == 200
    assert captured == {"offset": 1, "limit": 2}
    assert response.json()["offset"] == 1
    assert response.json()["limit"] == 2
    assert [item["id"] for item in response.json()["items"]] == [2, 3]


def test_list_knowledge_bases_with_defaults(monkeypatch):
    """测试知识库列表默认分页参数。"""
    captured = {}

    async def fake_list_all(self, offset=0, limit=20):
        captured.update(offset=offset, limit=limit)
        return []

    monkeypatch.setattr(KnowledgeBaseService, "list_all", fake_list_all)

    with create_client() as client:
        response = client.get("/api/v1/knowledge-bases")

    assert response.status_code == 200
    assert response.json() == {"items": [], "offset": 0, "limit": 20}
    assert captured == {"offset": 0, "limit": 20}


@pytest.mark.parametrize(
    "params",
    [
        {"offset": -1},
        {"limit": 0},
        {"limit": 101},
    ],
)
def test_list_rejects_invalid_pagination(params):
    """测试分页参数边界校验。"""
    with create_client() as client:
        response = client.get("/api/v1/knowledge-bases", params=params)

    assert response.status_code == 422


def test_get_knowledge_base(monkeypatch):
    """测试查询知识库详情。"""

    async def fake_get_by_id(self, knowledge_base_id):
        assert knowledge_base_id == 7
        return make_knowledge_base(7)

    monkeypatch.setattr(KnowledgeBaseService, "get_by_id", fake_get_by_id)

    with create_client() as client:
        response = client.get("/api/v1/knowledge-bases/7")

    assert response.status_code == 200
    assert response.json()["id"] == 7
    assert response.json()["name"] == "测试知识库"


def test_get_missing_knowledge_base(monkeypatch):
    """测试查询不存在的知识库返回 404。"""

    async def fake_get_by_id(self, knowledge_base_id):
        return None

    monkeypatch.setattr(KnowledgeBaseService, "get_by_id", fake_get_by_id)

    with create_client() as client:
        response = client.get("/api/v1/knowledge-bases/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "知识库不存在"


def test_knowledge_base_routes_registered():
    """测试正式应用已注册知识库管理路由。"""
    paths = app.openapi()["paths"]

    assert "/api/v1/knowledge-bases" in paths
    assert "post" in paths["/api/v1/knowledge-bases"]
    assert "get" in paths["/api/v1/knowledge-bases"]
    assert "get" in paths["/api/v1/knowledge-bases/{knowledge_base_id}"]
