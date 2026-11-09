"""KnowledgeFlow 文档异步 Repository。"""

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Document, DocumentChunk
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    """提供文档专属的数据查询能力。"""

    ALLOWED_STATUSES = frozenset({"pending", "processing", "completed", "failed"})

    def __init__(self, session: AsyncSession) -> None:
        """初始化文档 Repository。"""
        super().__init__(session, Document)

    @staticmethod
    def _validate_pagination(offset: int, limit: int) -> None:
        """校验分页参数。"""
        if offset < 0:
            raise ValueError("offset 不能小于 0")

        if limit <= 0:
            raise ValueError("limit 必须大于 0")

    async def get_by_id_with_chunks(
        self,
        document_id: int,
    ) -> Document | None:
        """
        根据主键查询文档，并预加载关联分块。

        Args:
            document_id: 文档主键。

        Returns:
            查询到的文档；不存在时返回 None。
        """
        statement = (
            select(Document)
            .options(selectinload(Document.chunks))
            .where(Document.id == document_id)
        )
        result = await self.session.scalars(statement)

        return result.one_or_none()

    async def get_by_content_hash(
        self,
        knowledge_base_id: int,
        content_hash: str,
    ) -> Document | None:
        """
        在指定知识库内根据 SHA-256 哈希查询文档。

        Args:
            knowledge_base_id: 所属知识库主键。
            content_hash: 64 位内容哈希值。

        Returns:
            查询到的文档；不存在时返回 None。
        """
        if not isinstance(content_hash, str):
            raise TypeError("content_hash 必须是字符串")

        if len(content_hash) != 64:
            raise ValueError("content_hash 长度必须为 64")

        statement = select(Document).where(
            Document.knowledge_base_id == knowledge_base_id,
            Document.content_hash == content_hash,
        )
        result = await self.session.scalars(statement)

        return result.one_or_none()

    async def get_by_knowledge_base(
        self,
        knowledge_base_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        """
        查询指定知识库下的文档，并支持分页。

        结果按文档主键升序排列，保证分页顺序稳定。

        Args:
            knowledge_base_id: 所属知识库主键。
            offset: 跳过的记录数量。
            limit: 最多返回的记录数量。

        Returns:
            符合条件的文档列表。
        """
        self._validate_pagination(offset, limit)

        statement = (
            select(Document)
            .where(Document.knowledge_base_id == knowledge_base_id)
            .order_by(Document.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)

        return list(result.all())

    async def get_by_knowledge_base_with_chunk_counts(
        self,
        knowledge_base_id: int,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[tuple[Document, int]], int]:
        """分页查询知识库文档及其分块数量，并返回文档总数。"""
        self._validate_pagination(offset, limit)

        count_statement = (
            select(func.count())
            .select_from(Document)
            .where(Document.knowledge_base_id == knowledge_base_id)
        )
        total = await self.session.scalar(count_statement)

        statement = (
            select(Document, func.count(DocumentChunk.id).label("chunk_count"))
            .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
            .where(Document.knowledge_base_id == knowledge_base_id)
            .group_by(Document.id)
            .order_by(Document.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)

        return list(result.all()), total or 0

    async def get_stale_processing(
        self,
        updated_before: datetime,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        """分页查询更新时间早于阈值的处理中状态文档。"""
        if not isinstance(updated_before, datetime):
            raise TypeError("updated_before 必须是 datetime 类型")
        if updated_before.tzinfo is not None and updated_before.utcoffset() is not None:
            raise ValueError("updated_before 必须是无时区 UTC 时间")

        self._validate_pagination(offset, limit)
        statement = (
            select(Document)
            .where(
                Document.status == "processing",
                Document.updated_at < updated_before,
            )
            .order_by(Document.updated_at.asc(), Document.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def claim_stale_processing(
        self,
        document_id: int,
        updated_before: datetime,
    ) -> bool:
        """原子认领超时文档，不自动提交事务。"""
        if isinstance(document_id, bool) or not isinstance(document_id, int):
            raise TypeError("document_id 必须是整数")
        if document_id <= 0:
            raise ValueError("document_id 必须大于 0")
        if not isinstance(updated_before, datetime):
            raise TypeError("updated_before 必须是 datetime 类型")
        if updated_before.tzinfo is not None and updated_before.utcoffset() is not None:
            raise ValueError("updated_before 必须是无时区 UTC 时间")

        statement = (
            update(Document)
            .where(
                Document.id == document_id,
                Document.status == "processing",
                Document.updated_at < updated_before,
            )
            .values(updated_at=func.current_timestamp())
            .returning(Document.id)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def get_by_status(
        self,
        status: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        """
        根据文档处理状态查询文档，并支持分页。

        Args:
            status: 文档处理状态。
            offset: 跳过的记录数量。
            limit: 最多返回的记录数量。

        Returns:
            符合条件的文档列表。

        Raises:
            TypeError: status 不是字符串。
            ValueError: 状态不受支持或分页参数无效。
        """
        if not isinstance(status, str):
            raise TypeError("status 必须是字符串")

        if status not in self.ALLOWED_STATUSES:
            raise ValueError(f"不支持的文档状态：{status}")

        self._validate_pagination(offset, limit)

        statement = (
            select(Document)
            .where(Document.status == status)
            .order_by(Document.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)

        return list(result.all())
