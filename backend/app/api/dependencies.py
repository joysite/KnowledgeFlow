"""KnowledgeFlow API 依赖注入模块。"""

from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import AgentExecutor, ToolRegistry, create_rag_tool
from app.db.session import get_db_session
from app.ingestion.chunk_processor import ChunkProcessor
from app.ingestion.chunker import TextChunker
from app.ingestion.token_counter import NomicTokenCounter
from app.services.bm25_search import BM25SearchService
from app.services.context_builder import ContextBuilder
from app.services.document_ingestion import DocumentIngestionService
from app.services.hybrid_search import HybridSearchService
from app.services.rag import RAGService
from app.services.vector_search import VectorSearchService


@lru_cache(maxsize=1)
def get_chunk_processor() -> ChunkProcessor:
    """创建并缓存应用级文档分块处理器。"""
    token_counter = NomicTokenCounter()

    chunker = TextChunker(
        max_chunk_size=1000,
        chunk_overlap=150,
        max_tokens=512,
        token_overlap=64,
        token_counter=token_counter,
    )

    return ChunkProcessor(
        chunker=chunker,
        token_counter=token_counter,
    )


async def get_document_ingestion_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> DocumentIngestionService:
    """组装当前请求使用的文档导入服务。"""
    vector_index_service = getattr(
        request.app.state,
        "vector_index_service",
        None,
    )

    if vector_index_service is None:
        raise RuntimeError("向量索引服务尚未初始化，请检查应用 lifespan 配置")

    return DocumentIngestionService(
        session=session,
        chunk_processor=get_chunk_processor(),
        vector_index_service=vector_index_service,
    )


async def get_vector_search_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> VectorSearchService:
    """组装当前请求使用的向量检索服务。"""
    embedding_service = getattr(
        request.app.state,
        "embedding_service",
        None,
    )
    vector_store = getattr(
        request.app.state,
        "vector_store",
        None,
    )

    if embedding_service is None or vector_store is None:
        raise RuntimeError("向量检索组件尚未初始化，请检查应用 lifespan 配置")

    return VectorSearchService(
        session=session,
        embedding_service=embedding_service,
        vector_store=vector_store,
    )


async def get_hybrid_search_service(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vector_search_service: VectorSearchService = Depends(get_vector_search_service),
) -> HybridSearchService:
    """组装当前请求使用的混合检索服务。"""
    return HybridSearchService(
        session=session,
        vector_search_service=vector_search_service,
        bm25_search_service=BM25SearchService(session),
    )


@lru_cache(maxsize=1)
def get_context_builder() -> ContextBuilder:
    """创建并缓存应用级 RAG 上下文构建器。"""
    return ContextBuilder()


async def get_rag_service(
    request: Request,
    hybrid_search_service: HybridSearchService = Depends(get_hybrid_search_service),
) -> RAGService:
    """组装当前请求使用的 RAG 服务。"""
    chat_service = getattr(request.app.state, "chat_service", None)

    if chat_service is None:
        raise RuntimeError("Ollama Chat 服务尚未初始化，请检查应用 lifespan 配置")

    return RAGService(
        hybrid_search_service=hybrid_search_service,
        context_builder=get_context_builder(),
        chat_service=chat_service,
    )


async def get_agent_executor(
    knowledge_base_id: int,
    request: Request,
    rag_service: RAGService = Depends(get_rag_service),
) -> AgentExecutor:
    """组装绑定当前知识库的 Agent 执行器。"""
    chat_service = getattr(request.app.state, "chat_service", None)

    if chat_service is None:
        raise RuntimeError("Ollama Chat 服务尚未初始化，请检查应用 lifespan 配置")

    registry = ToolRegistry()
    registry.register(
        create_rag_tool(
            rag_service,
            knowledge_base_id=knowledge_base_id,
        )
    )

    return AgentExecutor(
        chat_service=chat_service,
        tool_registry=registry,
    )
