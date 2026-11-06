"""KnowledgeFlow MCP 工具注册与实现。"""

from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from app.mcp_server.runtime import MCPRuntime
from app.services.bm25_search import BM25SearchService
from app.services.hybrid_search import HybridSearchService
from app.services.vector_search import VectorSearchService


async def search_knowledge(
    runtime: MCPRuntime,
    knowledge_base_id: int,
    query: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """执行知识库混合检索并返回来源信息。"""
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

    if runtime.embedding_service is None or runtime.vector_store is None:
        raise RuntimeError("MCPRuntime 检索服务尚未初始化")

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

        results = await hybrid_service.search(
            query=query,
            knowledge_base_id=knowledge_base_id,
            top_k=top_k,
        )

    return {
        "knowledge_base_id": knowledge_base_id,
        "query": query,
        "result_count": len(results),
        "results": [
            {
                "chunk_id": item.chunk_id,
                "document_id": item.document_id,
                "document_name": item.document_name,
                "chunk_index": item.chunk_index,
                "content": item.content,
                "token_count": item.token_count,
                "vector_distance": item.vector_distance,
                "bm25_score": item.bm25_score,
                "rrf_score": item.rrf_score,
            }
            for item in results
        ],
    }


def register_tools(server: FastMCP) -> None:
    """向 MCP Server 注册知识库工具。"""

    @server.tool(
        name="knowledge_search",
        description=(
            "检索指定 KnowledgeFlow 知识库中的相关内容。"
            "使用向量检索、BM25 和 RRF 融合排序，返回文档片段及来源信息。"
        ),
    )
    async def knowledge_search(
        knowledge_base_id: int,
        query: str,
        ctx: Context,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """检索知识库并返回匹配的文档片段。"""
        runtime = ctx.request_context.lifespan_context
        return await search_knowledge(
            runtime=runtime,
            knowledge_base_id=knowledge_base_id,
            query=query,
            top_k=top_k,
        )
