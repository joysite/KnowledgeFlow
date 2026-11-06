"""KnowledgeFlow 知识库管理 API。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.services.knowledge_base import KnowledgeBaseService

router = APIRouter(tags=["knowledge-bases"])


class KnowledgeBaseCreateRequest(BaseModel):
    """创建知识库请求。"""

    name: str = Field(min_length=1, max_length=128)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """去除名称首尾空白并拒绝空名称。"""
        value = value.strip()
        if not value:
            raise ValueError("知识库名称不能为空")
        return value


class KnowledgeBaseResponse(BaseModel):
    """知识库信息响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListResponse(BaseModel):
    """知识库分页响应。"""

    items: list[KnowledgeBaseResponse]
    offset: int
    limit: int


@router.post(
    "/knowledge-bases",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建知识库",
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeBaseResponse:
    """创建知识库并返回持久化记录。"""
    service = KnowledgeBaseService(session)

    try:
        knowledge_base = await service.create(
            name=payload.name,
            description=payload.description,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.get(
    "/knowledge-bases",
    response_model=KnowledgeBaseListResponse,
    summary="分页查询知识库",
)
async def list_knowledge_bases(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeBaseListResponse:
    """按主键升序分页查询知识库。"""
    service = KnowledgeBaseService(session)
    items = await service.list_all(offset=offset, limit=limit)

    return KnowledgeBaseListResponse(
        items=[KnowledgeBaseResponse.model_validate(item) for item in items],
        offset=offset,
        limit=limit,
    )


@router.get(
    "/knowledge-bases/{knowledge_base_id}",
    response_model=KnowledgeBaseResponse,
    summary="查询知识库详情",
)
async def get_knowledge_base(
    knowledge_base_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeBaseResponse:
    """根据 ID 查询知识库。"""
    service = KnowledgeBaseService(session)
    knowledge_base = await service.get_by_id(knowledge_base_id)

    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )

    return KnowledgeBaseResponse.model_validate(knowledge_base)
