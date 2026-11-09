"""KnowledgeFlow 知识库业务服务。"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeBase
from app.repositories import KnowledgeBaseRepository
from app.services.knowledge_base_locks import KnowledgeBaseOperationLocks


class KnowledgeBaseDeletingError(RuntimeError):
    """知识库正在删除，拒绝新的修改操作。"""


class KnowledgeBaseService:
    """处理知识库相关业务逻辑和事务管理。"""

    ALLOWED_UPDATE_FIELDS = frozenset({"name", "description"})

    def __init__(
        self,
        session: AsyncSession,
        operation_locks: KnowledgeBaseOperationLocks | None = None,
    ) -> None:
        """初始化知识库 Service。"""
        self.session = session
        self.operation_locks = operation_locks
        self.repository = KnowledgeBaseRepository(session)

    @staticmethod
    def _validate_name(name: str) -> str:
        """校验并规范化知识库名称。"""
        if not isinstance(name, str):
            raise TypeError("name 必须是字符串")

        normalized_name = name.strip()

        if not normalized_name:
            raise ValueError("知识库名称不能为空")

        if len(normalized_name) > 128:
            raise ValueError("知识库名称长度不能超过 128 个字符")

        return normalized_name

    @staticmethod
    def _validate_description(description: str | None) -> str | None:
        """校验知识库描述。"""
        if description is not None and not isinstance(description, str):
            raise TypeError("description 必须是字符串或 None")

        return description

    def _validate_update_data(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """校验知识库更新字段并返回规范化数据。"""
        if not isinstance(data, dict):
            raise TypeError("data 必须是字典")

        if not data:
            raise ValueError("更新数据不能为空")

        for field in data:
            if field not in self.ALLOWED_UPDATE_FIELDS:
                raise ValueError(f"不允许更新字段：{field}")

        validated_data = dict(data)

        if "name" in validated_data:
            validated_data["name"] = self._validate_name(validated_data["name"])

        if "description" in validated_data:
            validated_data["description"] = self._validate_description(
                validated_data["description"]
            )

        return validated_data

    async def create(
        self,
        name: str,
        description: str | None = None,
    ) -> KnowledgeBase:
        """
        创建知识库。

        成功后提交事务；失败时回滚事务。
        """
        normalized_name = self._validate_name(name)
        validated_description = self._validate_description(description)

        knowledge_base = KnowledgeBase(
            name=normalized_name,
            description=validated_description,
        )

        try:
            await self.repository.create(knowledge_base)
            await self.session.commit()
            await self.session.refresh(knowledge_base)
            return knowledge_base
        except BaseException:
            await self.session.rollback()
            raise

    async def get_by_id(
        self,
        knowledge_base_id: int,
    ) -> KnowledgeBase | None:
        """根据主键查询知识库。"""
        return await self.repository.get_by_id(knowledge_base_id)

    async def get_by_id_with_documents(
        self,
        knowledge_base_id: int,
    ) -> KnowledgeBase | None:
        """查询知识库并预加载关联文档。"""
        return await self.repository.get_by_id_with_documents(knowledge_base_id)

    async def list_all(
        self,
        offset: int = 0,
        limit: int = 20,
    ) -> list[KnowledgeBase]:
        """分页查询知识库。"""
        return await self.repository.list_all(offset=offset, limit=limit)

    async def list_all_with_document_counts(
        self,
        offset: int = 0,
        limit: int = 20,
        keyword: str | None = None,
    ) -> list[tuple[KnowledgeBase, int]]:
        """分页查询知识库及其文档数量，可按名称关键词过滤。"""
        return await self.repository.list_all_with_document_counts(
            offset=offset,
            limit=limit,
            keyword=keyword,
        )

    async def search_by_name(
        self,
        keyword: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[KnowledgeBase]:
        """根据名称关键词搜索知识库。"""
        return await self.repository.search_by_name(
            keyword,
            offset=offset,
            limit=limit,
        )

    async def update(
        self,
        knowledge_base_id: int,
        data: dict[str, Any],
    ) -> KnowledgeBase | None:
        """
        更新知识库信息。

        不存在时返回 None；成功后提交事务。
        """
        validated_data = self._validate_update_data(data)

        if self.operation_locks is None:
            return await self._update_locked(knowledge_base_id, validated_data)

        async with self.operation_locks.hold(knowledge_base_id):
            return await self._update_locked(knowledge_base_id, validated_data)

    async def _update_locked(
        self,
        knowledge_base_id: int,
        validated_data: dict[str, Any],
    ) -> KnowledgeBase | None:
        """在持有知识库操作锁时执行更新。"""
        knowledge_base = await self.repository.get_by_id(knowledge_base_id)

        if knowledge_base is None:
            return None

        if knowledge_base.status != "active":
            raise KnowledgeBaseDeletingError("知识库正在删除，暂时不能修改")

        try:
            await self.repository.update(
                knowledge_base,
                validated_data,
            )
            await self.session.commit()
            await self.session.refresh(knowledge_base)
            return knowledge_base
        except BaseException:
            await self.session.rollback()
            raise

    async def delete(self, knowledge_base_id: int) -> bool:
        """
        删除知识库。

        数据库通过外键级联删除关联文档和分块元数据。
        不负责删除磁盘上的原始文件。
        """
        knowledge_base = await self.repository.get_by_id(knowledge_base_id)

        if knowledge_base is None:
            return False

        try:
            await self.repository.delete(knowledge_base)
            await self.session.commit()
            return True
        except BaseException:
            await self.session.rollback()
            raise
