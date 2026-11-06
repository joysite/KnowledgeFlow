"""KnowledgeFlow BaseRepository 单元与 SQLite 集成测试。"""

import asyncio

import pytest

from app.models import KnowledgeBase
from app.repositories import BaseRepository


def test_repository_can_be_initialized(database):
    """测试 Repository 可以正常初始化。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            assert repository.session is session
            assert repository.model is KnowledgeBase

    asyncio.run(run_test())


def test_get_by_id_returns_existing_entity(database):
    """测试根据主键查询已存在的实体。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            entity = await repository.create(KnowledgeBase(name="测试知识库"))

            result = await repository.get_by_id(entity.id)

            assert result is entity
            assert result.name == "测试知识库"

    asyncio.run(run_test())


def test_get_by_id_returns_none_when_not_found(database):
    """测试查询不存在的主键时返回 None。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            result = await repository.get_by_id(999)

            assert result is None

    asyncio.run(run_test())


def test_get_all_returns_entities(database):
    """测试查询全部实体。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            await repository.create(KnowledgeBase(name="知识库一"))
            await repository.create(KnowledgeBase(name="知识库二"))

            result = await repository.get_all()

            assert len(result) == 2
            assert {item.name for item in result} == {
                "知识库一",
                "知识库二",
            }

    asyncio.run(run_test())


def test_get_all_supports_pagination(database):
    """测试分页查询。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            await repository.create(KnowledgeBase(name="知识库一"))
            await repository.create(KnowledgeBase(name="知识库二"))
            await repository.create(KnowledgeBase(name="知识库三"))

            first_page = await repository.get_all(offset=0, limit=2)
            second_page = await repository.get_all(offset=2, limit=2)

            assert len(first_page) == 2
            assert len(second_page) == 1

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("offset", "limit", "message"),
    [
        (-1, 10, "offset 不能小于 0"),
        (0, 0, "limit 必须大于 0"),
        (0, -1, "limit 必须大于 0"),
    ],
)
def test_get_all_rejects_invalid_pagination(
    database,
    offset,
    limit,
    message,
):
    """测试分页参数校验。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            with pytest.raises(ValueError, match=message):
                await repository.get_all(offset=offset, limit=limit)

    asyncio.run(run_test())


def test_create_adds_entity_and_flushes(database):
    """测试创建实体并刷新数据库状态。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            entity = await repository.create(KnowledgeBase(name="新建知识库"))

            assert entity.id is not None
            assert entity.name == "新建知识库"
            assert await session.get(KnowledgeBase, entity.id) is entity

            # Repository 不应主动提交事务。
            assert session.in_transaction()

    asyncio.run(run_test())


def test_create_rejects_wrong_entity_type(database):
    """测试创建时拒绝错误的实体类型。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            with pytest.raises(TypeError, match="KnowledgeBase"):
                await repository.create(object())

    asyncio.run(run_test())


def test_update_changes_specified_fields(database):
    """测试更新指定字段。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            entity = await repository.create(
                KnowledgeBase(
                    name="旧名称",
                    description="旧描述",
                )
            )

            result = await repository.update(
                entity,
                {
                    "name": "新名称",
                    "description": "新描述",
                },
            )

            assert result.name == "新名称"
            assert result.description == "新描述"

            await session.refresh(entity)

            assert entity.name == "新名称"
            assert entity.description == "新描述"

    asyncio.run(run_test())


def test_update_rejects_unknown_field(database):
    """测试更新时拒绝不存在的字段。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            entity = await repository.create(KnowledgeBase(name="原始名称"))

            with pytest.raises(ValueError, match="不存在可更新字段"):
                await repository.update(
                    entity,
                    {
                        "name": "不应修改",
                        "unknown_field": "无效字段",
                    },
                )

            assert entity.name == "原始名称"

    asyncio.run(run_test())


def test_update_rejects_primary_key(database):
    """测试更新时禁止修改主键。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            entity = await repository.create(KnowledgeBase(name="原始名称"))

            original_id = entity.id

            with pytest.raises(ValueError, match="不允许修改主键"):
                await repository.update(
                    entity,
                    {"id": 999},
                )

            assert entity.id == original_id

    asyncio.run(run_test())


def test_update_rejects_relationship_attribute(database):
    """测试更新时禁止修改 ORM 关系属性。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            entity = await repository.create(KnowledgeBase(name="测试知识库"))

            with pytest.raises(ValueError, match="不存在可更新字段"):
                await repository.update(
                    entity,
                    {"documents": []},
                )

    asyncio.run(run_test())


def test_delete_removes_entity(database):
    """测试删除实体。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            entity = await repository.create(KnowledgeBase(name="待删除知识库"))

            entity_id = entity.id

            await repository.delete(entity)

            result = await repository.get_by_id(entity_id)

            assert result is None

    asyncio.run(run_test())


def test_delete_does_not_commit_transaction(database):
    """测试删除操作不会主动提交事务。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            entity = await repository.create(KnowledgeBase(name="待删除知识库"))

            await repository.delete(entity)

            assert session.in_transaction()

    asyncio.run(run_test())


def test_update_rejects_non_dict_data(database):
    """测试更新时拒绝非字典参数。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = BaseRepository(session, KnowledgeBase)

            entity = await repository.create(KnowledgeBase(name="测试知识库"))

            with pytest.raises(TypeError, match="data 必须是字典"):
                await repository.update(entity, None)

    asyncio.run(run_test())
