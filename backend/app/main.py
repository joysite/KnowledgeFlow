"""KnowledgeFlow FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from app.api.middleware import UploadRequestSizeLimitMiddleware
from app.api.routes.agent import router as agent_router
from app.api.routes.documents import router as documents_router
from app.api.routes.knowledge_bases import router as knowledge_bases_router
from app.api.routes.rag import router as rag_router
from app.api.routes.search import router as search_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.engine import create_database_engine
from app.db.session import create_session_factory
from app.embeddings import EmbeddingService
from app.llm import OllamaChatService
from app.services.knowledge_base_locks import KnowledgeBaseOperationLocks
from app.services.vector_index import VectorIndexService
from app.vectorstore import ChromaVectorStore

logger = get_logger(__name__)


class HealthData(BaseModel):
    """健康检查数据模型。"""

    service: str
    status: str


class HealthResponse(BaseModel):
    """统一健康检查响应模型。"""

    code: int
    message: str
    data: HealthData


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """管理应用启动和关闭生命周期。"""
    setup_logging()

    engine = None
    ollama_client = None

    try:
        # 初始化数据库资源。
        engine = create_database_engine()
        application.state.database_engine = engine
        application.state.session_factory = create_session_factory(engine)

        # 创建应用级知识库操作锁，协调导入与删除等写操作。
        application.state.knowledge_base_operation_locks = KnowledgeBaseOperationLocks()

        # 创建应用级 HTTP 客户端，供 Embedding 服务复用。
        ollama_client = httpx.AsyncClient()
        application.state.ollama_client = ollama_client

        # 初始化向量化和向量存储服务。
        embedding_service = EmbeddingService(client=ollama_client)
        chat_service = OllamaChatService(client=ollama_client)
        vector_store = ChromaVectorStore()
        vector_index_service = VectorIndexService(
            embedding_service=embedding_service,
            vector_store=vector_store,
        )

        application.state.embedding_service = embedding_service
        application.state.chat_service = chat_service
        application.state.vector_store = vector_store
        application.state.vector_index_service = vector_index_service

        logger.info("KnowledgeFlow 后端服务启动成功")
        yield
    finally:
        # 先释放 HTTP 客户端，再释放数据库引擎。
        try:
            if ollama_client is not None:
                await ollama_client.aclose()
        finally:
            try:
                if engine is not None:
                    await engine.dispose()
            finally:
                # 清理应用状态中的共享资源引用。
                for name in (
                    "knowledge_base_operation_locks",
                    "vector_index_service",
                    "vector_store",
                    "embedding_service",
                    "chat_service",
                    "ollama_client",
                    "session_factory",
                    "database_engine",
                ):
                    if hasattr(application.state, name):
                        delattr(application.state, name)

                logger.info("KnowledgeFlow 后端服务正在关闭")


app = FastAPI(
    title="KnowledgeFlow API",
    description="基于混合检索与 Agent 工具调用的智能知识库系统",
    version="0.1.0",
    lifespan=lifespan,
)

# 限制文档上传请求体，额外预留 1 MiB multipart 封装空间。
app.add_middleware(
    UploadRequestSizeLimitMiddleware,
    max_size_bytes=get_settings().max_upload_size_bytes + 1024 * 1024,
)

# 注册文档上传 API。
app.include_router(knowledge_bases_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(rag_router, prefix="/api/v1")
app.include_router(agent_router, prefix="/api/v1")


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    tags=["系统"],
    summary="健康检查",
)
async def health_check() -> HealthResponse:
    """检查 KnowledgeFlow API 服务是否正常。"""
    logger.info("收到健康检查请求")

    return HealthResponse(
        code=200,
        message="服务运行正常",
        data=HealthData(
            service="KnowledgeFlow",
            status="healthy",
        ),
    )
