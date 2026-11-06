"""KnowledgeFlow 知识库 SQLite 集成测试。"""

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import KnowledgeBase


def test_knowledge_base_can_be_created_and_queried(database):
    """测试知识库能够成功插入和查询。"""
    engine, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(
                name="测试知识库",
                description="用于验证 SQLite ORM 操作",
            )

            session.add(knowledge_base)
            await session.commit()
            await session.refresh(knowledge_base)

            assert knowledge_base.id is not None
            assert knowledge_base.name == "测试知识库"
            assert knowledge_base.description == "用于验证 SQLite ORM 操作"
            assert isinstance(knowledge_base.created_at, datetime)
            assert isinstance(knowledge_base.updated_at, datetime)

            result = await session.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == knowledge_base.id,
                )
            )
            queried = result.scalar_one()

            assert queried.name == "测试知识库"
            assert queried.description == "用于验证 SQLite ORM 操作"

    asyncio.run(run_test())


def test_knowledge_base_description_can_be_null(database):
    """测试知识库描述允许为空。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(
                name="无描述知识库",
            )

            session.add(knowledge_base)
            await session.commit()
            await session.refresh(knowledge_base)

            assert knowledge_base.id is not None
            assert knowledge_base.description is None

    asyncio.run(run_test())


def test_knowledge_base_updated_at_changes_on_update(database):
    """测试 ORM 更新知识库时自动刷新更新时间。"""
    engine, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(
                name="更新时间测试",
            )

            session.add(knowledge_base)
            await session.commit()
            await session.refresh(knowledge_base)

            knowledge_base_id = knowledge_base.id

            # 将更新时间人为设置为过去，确保后续刷新能够被验证。
            async with engine.begin() as connection:
                await connection.exec_driver_sql(
                    """
                    UPDATE knowledge_bases
                    SET updated_at = '2000-01-01 00:00:00'
                    WHERE id = ?
                    """,
                    (knowledge_base_id,),
                )

            await session.refresh(knowledge_base)

            old_updated_at = knowledge_base.updated_at

            assert old_updated_at == datetime(2000, 1, 1)

            # 通过 ORM 修改名称，触发 onupdate。
            knowledge_base.name = "更新时间测试（已修改）"

            await session.commit()
            await session.refresh(knowledge_base)

            assert knowledge_base.name == "更新时间测试（已修改）"
            assert knowledge_base.updated_at > old_updated_at

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "invalid_name",
    [
        "",
        "   ",
        "x" * 129,
    ],
    ids=[
        "empty-name",
        "whitespace-name",
        "name-too-long",
    ],
)
def test_knowledge_base_rejects_invalid_name(
    database,
    invalid_name: str,
):
    """测试数据库拒绝空名称、纯空格名称和超长名称。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(
                name=invalid_name,
            )

            session.add(knowledge_base)

            with pytest.raises(IntegrityError):
                await session.commit()

            await session.rollback()

    asyncio.run(run_test())
