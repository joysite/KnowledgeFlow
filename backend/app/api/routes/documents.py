"""KnowledgeFlow 文档上传 API。"""

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_document_ingestion_service
from app.core.logging import get_logger
from app.db.session import get_db_session
from app.ingestion.storage import UploadTooLargeError
from app.ingestion.validators import FileValidationError
from app.services.document import DocumentService
from app.services.document_ingestion import (
    DocumentAlreadyExistsError,
    DocumentIngestionService,
    EmptyDocumentChunksError,
    EmptyDocumentContentError,
    KnowledgeBaseDeletingError,
    KnowledgeBaseNotFoundError,
)
from app.services.knowledge_base import KnowledgeBaseService

router = APIRouter(tags=["documents"])
logger = get_logger(__name__)


class DocumentUploadResponse(BaseModel):
    """文档上传成功响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    name: str
    file_type: str
    file_size: int
    status: str
    created_at: datetime


class DocumentListItemResponse(BaseModel):
    """知识库文档列表项。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_base_id: int
    name: str
    file_type: str
    file_size: int
    status: str
    error_message: str | None
    created_at: datetime
    chunk_count: int


class DocumentListResponse(BaseModel):
    """知识库文档分页列表响应。"""

    items: list[DocumentListItemResponse]
    offset: int
    limit: int
    total: int


class DocumentDuplicateResponse(BaseModel):
    """重复文档响应。"""

    code: int
    message: str
    document_id: int


@router.get(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=DocumentListResponse,
    summary="分页查询知识库文档",
)
async def list_knowledge_base_documents(
    knowledge_base_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentListResponse:
    """分页查询指定知识库的文档及其分块数量。"""
    knowledge_base_service = KnowledgeBaseService(session)
    knowledge_base = await knowledge_base_service.get_by_id(knowledge_base_id)

    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )

    if knowledge_base.status == "deleting":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="知识库正在删除，无法查询文档",
        )

    document_service = DocumentService(session)
    documents, total = await document_service.get_by_knowledge_base_with_chunk_counts(
        knowledge_base_id,
        offset=offset,
        limit=limit,
    )

    return DocumentListResponse(
        items=[
            DocumentListItemResponse.model_validate(
                {
                    **document.__dict__,
                    "chunk_count": chunk_count,
                }
            )
            for document, chunk_count in documents
        ],
        offset=offset,
        limit=limit,
        total=total,
    )


@router.post(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上传并导入文档",
)
async def upload_document(
    knowledge_base_id: int,
    file: UploadFile = File(...),
    ingestion_service: DocumentIngestionService = Depends(get_document_ingestion_service),
) -> DocumentUploadResponse:
    """上传文档并执行解析、分块和向量索引。"""
    knowledge_base_service = KnowledgeBaseService(ingestion_service.session)

    knowledge_base = await knowledge_base_service.get_by_id(knowledge_base_id)

    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )

    try:
        document = await ingestion_service.ingest(
            knowledge_base_id=knowledge_base_id,
            upload_file=file,
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except KnowledgeBaseDeletingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DocumentAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": 409,
                "message": "该知识库中已存在相同内容的文档",
                "document_id": exc.document_id,
            },
        ) from exc
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=str(exc),
        ) from exc
    except FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (EmptyDocumentContentError, EmptyDocumentChunksError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception:
        logger.exception(
            "文档上传导入失败，知识库 ID：%s，文件名：%s",
            knowledge_base_id,
            file.filename,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文档导入失败，请检查服务日志",
        ) from None

    return DocumentUploadResponse.model_validate(document)
