"""KnowledgeFlow 知识库异步 Repository。"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Document, KnowledgeBase
from app.repositories.base import BaseRepository


class KnowledgeBaseRepository(BaseRepository[KnowledgeBase]):
    """提供知识库专属的数据查询能力。"""

    def __init__(self, session: AsyncSession) -> None:
        """初始化知识库 Repository。"""
        super().__init__(session, KnowledgeBase)

    async def list_all(
        self,
        offset: int = 0,
        limit: int = 20,
    ) -> list[KnowledgeBase]:
        """分页查询知识库，按主键升序排列。"""
        if offset < 0:
            raise ValueError("offset 不能小于 0")
        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        statement = (
            select(KnowledgeBase).order_by(KnowledgeBase.id.asc()).offset(offset).limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def list_all_with_document_counts(
        self,
        offset: int = 0,
        limit: int = 20,
        keyword: str | None = None,
    ) -> list[tuple[KnowledgeBase, int]]:
        """分页查询知识库及其文档总数，可按名称关键词过滤。"""
        if offset < 0:
            raise ValueError("offset 不能小于 0")
        if limit <= 0:
            raise ValueError("limit 必须大于 0")
        if keyword is not None and not isinstance(keyword, str):
            raise TypeError("keyword 必须是字符串或 None")

        keyword = keyword.strip() if keyword is not None else None
        if keyword == "":
            keyword = None

        document_counts = (
            select(
                Document.knowledge_base_id.label("knowledge_base_id"),
                func.count(Document.id).label("document_count"),
            )
            .group_by(Document.knowledge_base_id)
            .subquery()
        )
        statement = select(
            KnowledgeBase,
            func.coalesce(document_counts.c.document_count, 0).label("document_count"),
        ).outerjoin(
            document_counts,
            KnowledgeBase.id == document_counts.c.knowledge_base_id,
        )
        if keyword is not None:
            statement = statement.where(KnowledgeBase.name.contains(keyword, autoescape=True))
        statement = statement.order_by(KnowledgeBase.id.asc()).offset(offset).limit(limit)
        result = await self.session.execute(statement)
        return [(knowledge_base, count) for knowledge_base, count in result.all()]

    async def get_by_id_with_documents(
        self,
        knowledge_base_id: int,
    ) -> KnowledgeBase | None:
        """
        根据主键查询知识库，并预加载关联文档。

        Args:
            knowledge_base_id: 知识库主键。

        Returns:
            查询到的知识库；不存在时返回 None。
        """
        statement = (
            select(KnowledgeBase)
            .options(selectinload(KnowledgeBase.documents))
            .where(KnowledgeBase.id == knowledge_base_id)
        )
        result = await self.session.scalars(statement)

        return result.one_or_none()

    async def search_by_name(
        self,
        keyword: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[KnowledgeBase]:
        """
        根据名称关键词搜索知识库，并支持分页。

        使用包含匹配，允许返回多个同名知识库。
        搜索结果按主键升序排列，保证分页顺序稳定。

        Args:
            keyword: 知识库名称关键词。
            offset: 跳过的记录数量。
            limit: 最多返回的记录数量。

        Returns:
            符合条件的知识库列表。

        Raises:
            TypeError: keyword 不是字符串。
            ValueError: 关键词为空或分页参数无效。
        """
        if not isinstance(keyword, str):
            raise TypeError("keyword 必须是字符串")

        keyword = keyword.strip()
        if not keyword:
            raise ValueError("keyword 不能为空")

        if offset < 0:
            raise ValueError("offset 不能小于 0")

        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        statement = (
            select(KnowledgeBase)
            .where(KnowledgeBase.name.contains(keyword, autoescape=True))
            .order_by(KnowledgeBase.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)

        return list(result.all())
