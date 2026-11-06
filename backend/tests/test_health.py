"""KnowledgeFlow 健康检查接口测试。"""

from fastapi.testclient import TestClient

from app.main import app


def test_health_check_returns_success():
    """测试健康检查接口返回成功。"""
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200


def test_health_check_response_structure():
    """测试健康检查接口响应结构。"""
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    result = response.json()

    assert result["code"] == 200
    assert result["message"] == "服务运行正常"
    assert result["data"]["service"] == "KnowledgeFlow"
    assert result["data"]["status"] == "healthy"


def test_health_check_response_content_type():
    """测试健康检查接口返回 JSON。"""
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert "application/json" in response.headers["content-type"]
