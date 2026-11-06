"""KnowledgeFlow 文档分块异步 Repository。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Document, DocumentChunk
from app.repositories.base import BaseRepository


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    """提供文档分块专属的数据查询能力。"""

    def __init__(self, session: AsyncSession) -> None:
        """初始化文档分块 Repository。"""
        super().__init__(session, DocumentChunk)

    async def create_many(
        self,
        entities: list[DocumentChunk],
    ) -> list[DocumentChunk]:
        """
        批量创建文档分块。

        只执行一次 flush，不提交事务，由上层 Service 管理事务。

        Args:
            entities: 待创建的文档分块列表。

        Returns:
            创建后的文档分块列表。

        Raises:
            TypeError: 输入不是列表，或列表中包含非 DocumentChunk 对象。
        """
        if not isinstance(entities, list):
            raise TypeError("entities 必须是列表")

        if not entities:
            return []

        # 先校验全部对象，避免部分数据进入 Session。
        if not all(isinstance(entity, DocumentChunk) for entity in entities):
            raise TypeError("entities 中的元素必须是 DocumentChunk 类型")

        self.session.add_all(entities)
        await self.session.flush()

        return entities

    @staticmethod
    def _validate_pagination(offset: int, limit: int) -> None:
        """校验分页参数。"""
        if offset < 0:
            raise ValueError("offset 不能小于 0")

        if limit <= 0:
            raise ValueError("limit 必须大于 0")

    async def get_by_document(
        self,
        document_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[DocumentChunk]:
        """
        查询指定文档的分块，并按照分块序号升序排列。

        Args:
            document_id: 所属文档主键。
            offset: 跳过的记录数量。
            limit: 最多返回的记录数量。

        Returns:
            按 chunk_index 升序排列的分块列表。
        """
        self._validate_pagination(offset, limit)

        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)

        return list(result.all())

    async def get_by_ids(
        self,
        knowledge_base_id: int,
        chunk_ids: list[int],
    ) -> list[DocumentChunk]:
        """批量查询指定知识库中已完成文档的分块。"""
        if isinstance(knowledge_base_id, bool) or not isinstance(knowledge_base_id, int):
            raise TypeError("knowledge_base_id 必须是整数")
        if knowledge_base_id <= 0:
            raise ValueError("knowledge_base_id 必须大于 0")
        if not isinstance(chunk_ids, list) or not chunk_ids:
            raise ValueError("chunk_ids 必须是非空列表")
        if any(isinstance(item, bool) or not isinstance(item, int) for item in chunk_ids):
            raise TypeError("chunk_ids 中的元素必须是整数")
        if any(item <= 0 for item in chunk_ids):
            raise ValueError("chunk ID 必须大于 0")
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunk_ids 不能包含重复 ID")

        statement = (
            select(DocumentChunk)
            .options(selectinload(DocumentChunk.document))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                DocumentChunk.id.in_(chunk_ids),
                Document.knowledge_base_id == knowledge_base_id,
                Document.status == "completed",
            )
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_by_knowledge_base(
        self,
        knowledge_base_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[DocumentChunk]:
        """分页查询指定知识库中已完成文档的全部分块。"""
        if isinstance(knowledge_base_id, bool) or not isinstance(knowledge_base_id, int):
            raise TypeError("knowledge_base_id 必须是整数")
        if knowledge_base_id <= 0:
            raise ValueError("knowledge_base_id 必须大于 0")

        self._validate_pagination(offset, limit)

        statement = (
            select(DocumentChunk)
            .options(selectinload(DocumentChunk.document))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.knowledge_base_id == knowledge_base_id,
                Document.status == "completed",
            )
            .order_by(
                DocumentChunk.document_id.asc(),
                DocumentChunk.chunk_index.asc(),
                DocumentChunk.id.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_by_document_and_index(
        self,
        document_id: int,
        chunk_index: int,
    ) -> DocumentChunk | None:
        """
        根据文档主键和分块序号查询指定分块。

        Args:
            document_id: 所属文档主键。
            chunk_index: 文档内分块序号。

        Returns:
            查询到的分块；不存在时返回 None。
        """
        statement = select(DocumentChunk).where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.chunk_index == chunk_index,
        )
        result = await self.session.scalars(statement)

        return result.one_or_none()
