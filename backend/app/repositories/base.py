"""KnowledgeFlow 通用异步 Repository 基类。"""

from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base


class BaseRepository[ModelT: Base]:
    """提供 ORM 模型通用的异步 CRUD 数据访问能力。"""

    def __init__(
        self,
        session: AsyncSession,
        model: type[ModelT],
    ) -> None:
        """
        初始化 Repository。

        Args:
            session: 当前业务使用的异步数据库会话。
            model: 当前 Repository 操作的 ORM 模型类型。
        """
        self.session = session
        self.model = model

        mapper = inspect(model)
        self._column_names = {attribute.key for attribute in mapper.column_attrs}
        self._primary_key_names = {
            mapper.get_property_by_column(column).key for column in mapper.primary_key
        }

    async def get_by_id(self, entity_id: int) -> ModelT | None:
        """
        根据主键查询实体。

        Args:
            entity_id: 实体主键。

        Returns:
            查询到的实体；不存在时返回 None。
        """
        return await self.session.get(self.model, entity_id)

    async def get_all(
        self,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ModelT]:
        """
        分页查询实体。

        Args:
            offset: 跳过的记录数量。
            limit: 最多返回的记录数量。

        Returns:
            当前分页中的实体列表。

        Raises:
            ValueError: offset 小于 0 或 limit 小于等于 0。
        """
        if offset < 0:
            raise ValueError("offset 不能小于 0")

        if limit <= 0:
            raise ValueError("limit 必须大于 0")

        statement = select(self.model).offset(offset).limit(limit)
        result = await self.session.scalars(statement)

        return list(result.all())

    async def create(self, entity: ModelT) -> ModelT:
        """
        添加实体并刷新数据库状态。

        不提交事务，事务提交由上层 Service 负责。

        Args:
            entity: 待添加的 ORM 实体。

        Returns:
            添加后的 ORM 实体。
        """
        if not isinstance(entity, self.model):
            raise TypeError(f"entity 必须是 {self.model.__name__} 类型")

        self.session.add(entity)
        await self.session.flush()

        return entity

    async def update(
        self,
        entity: ModelT,
        data: dict[str, Any],
    ) -> ModelT:
        """
        更新实体的指定字段并刷新数据库状态。

        只允许更新 ORM 映射的普通列字段，不允许修改主键或关系属性。
        不提交事务，事务提交由上层 Service 负责。

        Args:
            entity: 待更新的 ORM 实体。
            data: 字段名称与新值组成的字典。

        Returns:
            更新后的 ORM 实体。

        Raises:
            TypeError: entity 类型不正确或 data 不是字典。
            ValueError: 字段不存在、字段不可更新或主键被修改。
        """
        if not isinstance(entity, self.model):
            raise TypeError(f"entity 必须是 {self.model.__name__} 类型")

        if not isinstance(data, dict):
            raise TypeError("data 必须是字典")

        # 先完成全部字段校验，避免无效输入造成部分修改。
        for field in data:
            if field not in self._column_names:
                raise ValueError(f"模型不存在可更新字段：{field}")

            if field in self._primary_key_names:
                raise ValueError(f"不允许修改主键字段：{field}")

        for field, value in data.items():
            setattr(entity, field, value)

        await self.session.flush()

        return entity

    async def delete(self, entity: ModelT) -> None:
        """
        删除实体并刷新数据库状态。

        不提交事务，事务提交由上层 Service 负责。

        Args:
            entity: 待删除的 ORM 实体。
        """
        if not isinstance(entity, self.model):
            raise TypeError(f"entity 必须是 {self.model.__name__} 类型")

        await self.session.delete(entity)
        await self.session.flush()
