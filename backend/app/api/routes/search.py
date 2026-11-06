"""KnowledgeFlow 知识库检索 API。"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.dependencies import get_hybrid_search_service
from app.core.logging import get_logger
from app.services.hybrid_search import HybridSearchService
from app.services.knowledge_base import KnowledgeBaseService

router = APIRouter(tags=["search"])
logger = get_logger(__name__)


class SearchRequest(BaseModel):
    """知识库检索请求。"""

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


class SearchResultItem(BaseModel):
    """单条混合检索结果。"""

    model_config = ConfigDict(from_attributes=True)

    chunk_id: int
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    token_count: int
    vector_distance: float | None = None
    bm25_score: float | None = None
    rrf_score: float


class SearchResponse(BaseModel):
    """知识库检索响应。"""

    knowledge_base_id: int
    query: str
    results: list[SearchResultItem]


@router.post(
    "/knowledge-bases/{knowledge_base_id}/search",
    response_model=SearchResponse,
    summary="检索知识库",
)
async def search_knowledge_base(
    knowledge_base_id: int,
    payload: SearchRequest,
    search_service: HybridSearchService = Depends(get_hybrid_search_service),
) -> SearchResponse:
    """执行 BM25 与向量混合检索。"""
    knowledge_base_service = KnowledgeBaseService(search_service.session)
    knowledge_base = await knowledge_base_service.get_by_id(knowledge_base_id)

    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )

    try:
        results = await search_service.search(
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
            "知识库混合检索失败，知识库 ID：%s",
            knowledge_base_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="知识库检索失败，请检查服务日志",
        ) from None

    return SearchResponse(
        knowledge_base_id=knowledge_base_id,
        query=payload.query,
        results=[SearchResultItem.model_validate(result) for result in results],
    )
