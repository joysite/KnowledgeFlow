"""KnowledgeFlow 文档上传 API 测试。"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_document_ingestion_service
from app.api.routes.documents import router
from app.ingestion.storage import UploadTooLargeError
from app.ingestion.validators import FileValidationError
from app.services.document_ingestion import (
    DocumentAlreadyExistsError,
    EmptyDocumentChunksError,
    EmptyDocumentContentError,
)
from app.services.knowledge_base import KnowledgeBaseService


class FakeIngestionService:
    """隔离真实文件处理和向量索引的模拟导入服务。"""

    def __init__(self, error=None):
        self.session = object()
        self.error = error
        self.called = False

    async def ingest(self, knowledge_base_id, upload_file):
        self.called = True

        if self.error is not None:
            raise self.error

        return SimpleNamespace(
            id=10,
            knowledge_base_id=knowledge_base_id,
            name=upload_file.filename,
            file_type="txt",
            file_size=upload_file.size or 0,
            status="completed",
            created_at=datetime(2026, 11, 5, 10, 0, 0),
        )


def create_client(monkeypatch, service, knowledge_base_exists=True):
    """创建不启动真实应用生命周期的独立测试客户端。"""

    async def fake_get_by_id(self, knowledge_base_id):
        if knowledge_base_exists:
            return object()
        return None

    monkeypatch.setattr(KnowledgeBaseService, "get_by_id", fake_get_by_id)

    application = FastAPI()
    application.include_router(router, prefix="/api/v1")
    application.dependency_overrides[get_document_ingestion_service] = lambda: service

    return TestClient(application)


def upload(client):
    """发送统一格式的 TXT 上传请求。"""
    return client.post(
        "/api/v1/knowledge-bases/1/documents",
        files={"file": ("test.txt", b"hello knowledge flow", "text/plain")},
    )


def test_upload_document_returns_created_response(monkeypatch):
    """测试上传成功并返回文档信息。"""
    service = FakeIngestionService()
    client = create_client(monkeypatch, service)

    response = upload(client)

    assert response.status_code == 201
    assert response.json() == {
        "id": 10,
        "knowledge_base_id": 1,
        "name": "test.txt",
        "file_type": "txt",
        "file_size": 20,
        "status": "completed",
        "created_at": "2026-11-05T10:00:00",
    }
    assert service.called is True


def test_upload_document_returns_not_found_for_missing_knowledge_base(
    monkeypatch,
):
    """测试知识库不存在时返回 404，且不执行导入。"""
    service = FakeIngestionService()
    client = create_client(
        monkeypatch,
        service,
        knowledge_base_exists=False,
    )

    response = upload(client)

    assert response.status_code == 404
    assert response.json()["detail"] == "知识库不存在"
    assert service.called is False


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            DocumentAlreadyExistsError(42),
            409,
            {
                "code": 409,
                "message": "该知识库中已存在相同内容的文档",
                "document_id": 42,
            },
        ),
        (
            UploadTooLargeError("文件大小超过限制"),
            413,
            "文件大小超过限制",
        ),
        (
            FileValidationError("不支持的文件类型"),
            400,
            "不支持的文件类型",
        ),
        (
            EmptyDocumentContentError("文档清洗后没有有效文本内容"),
            422,
            "文档清洗后没有有效文本内容",
        ),
        (
            EmptyDocumentChunksError("文档没有产生有效分块"),
            422,
            "文档没有产生有效分块",
        ),
    ],
)
def test_upload_document_maps_business_errors(
    monkeypatch,
    error,
    expected_status,
    expected_detail,
):
    """测试业务异常映射为对应 HTTP 状态码。"""
    service = FakeIngestionService(error=error)
    client = create_client(monkeypatch, service)

    response = upload(client)

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail
    assert service.called is True


def test_upload_document_hides_internal_error(monkeypatch):
    """测试内部异常返回通用错误，不泄露异常详情。"""
    service = FakeIngestionService(error=RuntimeError("内部数据库连接信息"))
    client = create_client(monkeypatch, service)

    response = upload(client)

    assert response.status_code == 500
    assert response.json()["detail"] == "文档导入失败，请检查服务日志"
    assert "内部数据库连接信息" not in response.text


def test_document_upload_route_is_registered_in_main_app():
    """测试文档上传路由已注册到正式 FastAPI 应用。"""
    from app.main import app

    schema = app.openapi()
    path = "/api/v1/knowledge-bases/{knowledge_base_id}/documents"

    assert path in schema["paths"]
    assert "post" in schema["paths"][path]
