"""KnowledgeFlow API 依赖注入测试。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.api.dependencies import (
    get_chunk_processor,
    get_document_ingestion_service,
)
from app.services.document_ingestion import DocumentIngestionService
from app.services.vector_index import VectorIndexService


def create_request(vector_index_service=None):
    """创建包含指定向量服务的模拟请求。"""
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                vector_index_service=vector_index_service,
            )
        )
    )


def create_vector_index_service():
    """创建不连接外部服务的向量索引服务实例。"""
    return VectorIndexService(
        embedding_service=object(),
        vector_store=object(),
    )


def test_chunk_processor_is_cached():
    """测试分块处理器缓存及其配置。"""
    first = get_chunk_processor()
    second = get_chunk_processor()

    assert first is second
    assert first.chunker.max_chunk_size == 1000
    assert first.chunker.chunk_overlap == 150
    assert first.chunker.max_tokens == 512
    assert first.chunker.token_overlap == 64
    assert first.chunker.token_counter is first.token_counter


def test_document_ingestion_service_injects_dependencies(database):
    """测试数据库会话和向量索引服务正确注入。"""
    _, session_factory = database
    vector_service = create_vector_index_service()
    request = create_request(vector_service)

    async def run_test():
        async with session_factory() as session:
            service = await get_document_ingestion_service(
                request=request,
                session=session,
            )

            assert isinstance(service, DocumentIngestionService)
            assert service.session is session
            assert service.vector_index_service is vector_service
            assert service.chunk_processor is get_chunk_processor()

    asyncio.run(run_test())


def test_document_ingestion_service_uses_current_session(database):
    """测试不同请求使用各自的数据库会话。"""
    _, session_factory = database
    request = create_request(create_vector_index_service())

    async def run_test():
        async with session_factory() as first_session:
            first_service = await get_document_ingestion_service(
                request=request,
                session=first_session,
            )

        async with session_factory() as second_session:
            second_service = await get_document_ingestion_service(
                request=request,
                session=second_session,
            )

        assert first_service.session is first_session
        assert second_service.session is second_session
        assert first_service.session is not second_service.session
        assert first_service.chunk_processor is second_service.chunk_processor

    asyncio.run(run_test())


def test_document_ingestion_service_rejects_missing_vector_service():
    """测试向量索引服务未初始化时给出明确异常。"""
    request = create_request()

    async def run_test():
        with pytest.raises(
            RuntimeError,
            match="向量索引服务尚未初始化",
        ):
            await get_document_ingestion_service(
                request=request,
                session=None,
            )

    asyncio.run(run_test())
