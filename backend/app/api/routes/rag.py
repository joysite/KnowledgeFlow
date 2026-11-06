"""KnowledgeFlow 知识库 RAG 问答 API。"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.api.dependencies import get_rag_service
from app.core.logging import get_logger
from app.services.knowledge_base import KnowledgeBaseService
from app.services.rag import RAGService

router = APIRouter(tags=["rag"])
logger = get_logger(__name__)


class RAGRequest(BaseModel):
    """知识库问答请求。"""

    query: str = Field(min_length=1, max_length=10000)
    top_k: int = Field(default=5, strict=True, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        """去除查询文本首尾空白。"""
        value = value.strip()
        if not value:
            raise ValueError("查询文本不能为空")
        return value


class RAGSourceItem(BaseModel):
    """RAG 回答引用的来源分块。"""

    source_id: int
    chunk_id: int
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    rrf_score: float


class RAGResponseModel(BaseModel):
    """知识库问答响应。"""

    knowledge_base_id: int
    query: str
    answer: str
    sources: list[RAGSourceItem]
    retrieved_count: int
    context_token_count: int


@router.post(
    "/knowledge-bases/{knowledge_base_id}/rag",
    response_model=RAGResponseModel,
    summary="基于知识库生成回答",
)
async def answer_knowledge_base(
    knowledge_base_id: int,
    payload: RAGRequest,
    rag_service: RAGService = Depends(get_rag_service),
) -> RAGResponseModel:
    """检索知识库上下文并生成带来源引用的回答。"""
    knowledge_base_service = KnowledgeBaseService(rag_service.hybrid_search_service.session)
    knowledge_base = await knowledge_base_service.get_by_id(knowledge_base_id)

    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )

    try:
        result = await rag_service.answer(
            query=payload.query,
            knowledge_base_id=knowledge_base_id,
            top_k=payload.top_k,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception:
        logger.exception(
            "知识库 RAG 问答失败，知识库 ID：%s",
            knowledge_base_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="知识库问答失败，请检查服务日志",
        ) from None

    return RAGResponseModel(
        knowledge_base_id=knowledge_base_id,
        query=result.query,
        answer=result.answer,
        sources=[
            RAGSourceItem(
                source_id=source.source_id,
                chunk_id=source.chunk_id,
                document_id=source.document_id,
                document_name=source.document_name,
                chunk_index=source.chunk_index,
                content=source.content,
                rrf_score=source.rrf_score,
            )
            for source in result.sources
        ],
        retrieved_count=result.retrieved_count,
        context_token_count=result.context_token_count,
    )
