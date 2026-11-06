"""KnowledgeFlow MCP RAG 问答工具。"""

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from app.mcp_server.runtime import MCPRuntime
from app.services.bm25_search import BM25SearchService
from app.services.context_builder import ContextBuilder
from app.services.hybrid_search import HybridSearchService
from app.services.rag import RAGService
from app.services.vector_search import VectorSearchService


async def answer_knowledge(
    runtime: MCPRuntime,
    knowledge_base_id: int,
    query: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """调用现有 RAGService 生成带来源引用的回答。"""
    if isinstance(knowledge_base_id, bool) or not isinstance(knowledge_base_id, int):
        raise TypeError("knowledge_base_id 必须是整数")
    if knowledge_base_id <= 0:
        raise ValueError("knowledge_base_id 必须大于 0")

    if not isinstance(query, str) or not query.strip():
        raise ValueError("查询文本不能为空")

    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise TypeError("top_k 必须是整数")
    if not 1 <= top_k <= 100:
        raise ValueError("top_k 必须在 1 到 100 之间")

    if (
        runtime.embedding_service is None
        or runtime.vector_store is None
        or runtime.chat_service is None
    ):
        raise RuntimeError("MCPRuntime RAG 服务尚未初始化")

    query = query.strip()

    async with runtime.create_session() as session:
        vector_service = VectorSearchService(
            session=session,
            embedding_service=runtime.embedding_service,
            vector_store=runtime.vector_store,
        )
        hybrid_service = HybridSearchService(
            session=session,
            vector_search_service=vector_service,
            bm25_search_service=BM25SearchService(session),
        )
        rag_service = RAGService(
            hybrid_search_service=hybrid_service,
            context_builder=ContextBuilder(),
            chat_service=runtime.chat_service,
        )

        result = await rag_service.answer(
            query=query,
            knowledge_base_id=knowledge_base_id,
            top_k=top_k,
        )

    return {
        "knowledge_base_id": knowledge_base_id,
        "query": result.query,
        "answer": result.answer,
        "retrieved_count": result.retrieved_count,
        "context_token_count": result.context_token_count,
        "sources": [
            {
                "source_id": source.source_id,
                "chunk_id": source.chunk_id,
                "document_id": source.document_id,
                "document_name": source.document_name,
                "chunk_index": source.chunk_index,
                "content": source.content,
                "rrf_score": source.rrf_score,
            }
            for source in result.sources
        ],
    }


def register_rag_tool(server: FastMCP) -> None:
    """注册知识库 RAG 问答工具。"""

    @server.tool(
        name="knowledge_rag",
        description=(
            "根据指定 KnowledgeFlow 知识库回答问题。"
            "使用混合检索和本地大语言模型生成答案，并返回文档来源引用。"
        ),
    )
    async def knowledge_rag(
        knowledge_base_id: int,
        query: str,
        ctx: Context,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """执行知识库 RAG 问答。"""
        runtime = ctx.request_context.lifespan_context
        return await answer_knowledge(
            runtime=runtime,
            knowledge_base_id=knowledge_base_id,
            query=query,
            top_k=top_k,
        )
