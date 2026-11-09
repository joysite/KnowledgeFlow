"""KnowledgeFlow 知识库管理 API。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_knowledge_base_deletion_service,
    get_knowledge_base_operation_locks,
)
from app.db.session import get_db_session
from app.services.knowledge_base import (
    KnowledgeBaseDeletingError,
    KnowledgeBaseService,
)
from app.services.knowledge_base_deletion import (
    KnowledgeBaseDeletionError,
    KnowledgeBaseDeletionService,
)
from app.services.knowledge_base_locks import KnowledgeBaseOperationLocks

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


class KnowledgeBaseUpdateRequest(BaseModel):
    """更新知识库请求。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        """去除名称首尾空白并拒绝空名称。"""
        if value is None:
            return None

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
    status: str = "active"
    deletion_error: str | None = None


class KnowledgeBaseListItemResponse(KnowledgeBaseResponse):
    """知识库列表项，附带文档数量。"""

    document_count: int = Field(ge=0)


class KnowledgeBaseListResponse(BaseModel):
    """知识库分页响应。"""

    items: list[KnowledgeBaseListItemResponse]
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
    keyword: str | None = Query(default=None, max_length=128),
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeBaseListResponse:
    """按名称关键词过滤并分页查询知识库及文档数量。"""
    service = KnowledgeBaseService(session)
    items = await service.list_all_with_document_counts(
        offset=offset,
        limit=limit,
        keyword=keyword,
    )

    return KnowledgeBaseListResponse(
        items=[
            KnowledgeBaseListItemResponse.model_validate(
                {
                    **KnowledgeBaseResponse.model_validate(knowledge_base).model_dump(),
                    "document_count": document_count,
                }
            )
            for knowledge_base, document_count in items
        ],
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


@router.patch(
    "/knowledge-bases/{knowledge_base_id}",
    response_model=KnowledgeBaseResponse,
    summary="更新知识库",
)
async def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    operation_locks: KnowledgeBaseOperationLocks = Depends(get_knowledge_base_operation_locks),
) -> KnowledgeBaseResponse:
    """更新知识库名称或描述。"""
    service = KnowledgeBaseService(session, operation_locks)

    try:
        knowledge_base = await service.update(
            knowledge_base_id,
            payload.model_dump(exclude_unset=True),
        )
    except KnowledgeBaseDeletingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )

    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.delete(
    "/knowledge-bases/{knowledge_base_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="彻底删除知识库",
)
async def delete_knowledge_base(
    knowledge_base_id: int,
    deletion_service: KnowledgeBaseDeletionService = Depends(get_knowledge_base_deletion_service),
) -> Response:
    """清理知识库关联的向量、上传文件和数据库记录。"""
    try:
        deleted = await deletion_service.delete(knowledge_base_id)
    except KnowledgeBaseDeletionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
