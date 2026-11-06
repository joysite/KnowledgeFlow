"""KnowledgeFlow Document SQLite 集成测试。"""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.models import Document, KnowledgeBase


async def create_knowledge_base(
    session,
    name: str = "测试知识库",
) -> KnowledgeBase:
    """创建测试知识库。"""
    knowledge_base = KnowledgeBase(name=name)
    session.add(knowledge_base)
    await session.flush()

    return knowledge_base


async def create_document(
    session,
    knowledge_base_id: int,
    **kwargs,
) -> Document:
    """创建测试文档。"""
    document_data = {
        "knowledge_base_id": knowledge_base_id,
        "name": "测试文档.pdf",
        "file_type": "pdf",
        "file_path": "uploads/test/document.pdf",
        "file_size": 1024,
        "content_hash": "a" * 64,
    }
    document_data.update(kwargs)

    document = Document(**document_data)
    session.add(document)

    return document


def test_document_can_be_created_and_queried(database):
    """测试文档能够成功插入和查询。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)

            document = await create_document(
                session,
                knowledge_base.id,
            )

            await session.commit()
            await session.refresh(document)

            assert document.id is not None
            assert document.knowledge_base_id == knowledge_base.id
            assert document.name == "测试文档.pdf"
            assert document.file_type == "pdf"
            assert document.file_path == "uploads/test/document.pdf"
            assert document.file_size == 1024
            assert document.content_hash == "a" * 64
            assert document.status == "pending"
            assert document.error_message is None
            assert document.created_at is not None
            assert document.updated_at is not None

            result = await session.execute(
                select(Document)
                .options(selectinload(Document.knowledge_base))
                .where(Document.id == document.id)
            )
            queried = result.scalar_one()

            assert queried.name == "测试文档.pdf"
            assert queried.knowledge_base_id == knowledge_base.id

    asyncio.run(run_test())


def test_document_relationship_can_be_loaded(database):
    """测试文档与知识库的双向 ORM 关系。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)

            document = await create_document(
                session,
                knowledge_base.id,
            )

            await session.commit()

            # 查询 Document，并预加载所属知识库。
            result = await session.execute(
                select(Document)
                .options(selectinload(Document.knowledge_base))
                .where(Document.id == document.id)
            )
            queried_document = result.scalar_one()

            assert queried_document.knowledge_base.id == knowledge_base.id

            # 查询 KnowledgeBase，并预加载关联文档。
            result = await session.execute(
                select(KnowledgeBase)
                .options(selectinload(KnowledgeBase.documents))
                .where(KnowledgeBase.id == knowledge_base.id)
            )
            queried_knowledge_base = result.scalar_one()

            assert len(queried_knowledge_base.documents) == 1
            assert queried_knowledge_base.documents[0].id == document.id

    asyncio.run(run_test())


def test_document_same_hash_is_rejected_in_same_knowledge_base(database):
    """测试同一知识库内不允许重复内容哈希。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)

            # 第一份文档：正常写入。
            await create_document(
                session,
                knowledge_base.id,
            )
            await session.commit()

            # 第二份文档：使用相同哈希，应该触发唯一约束。
            await create_document(
                session,
                knowledge_base.id,
                name="重复内容.pdf",
                file_path="uploads/test/duplicate.pdf",
            )

            with pytest.raises(IntegrityError):
                await session.commit()

            await session.rollback()


def test_document_same_hash_is_allowed_in_different_knowledge_bases(database):
    """测试不同知识库允许保存相同内容的文档。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            # 创建两个不同的知识库。
            first_kb = await create_knowledge_base(
                session,
                "第一个知识库",
            )
            second_kb = await create_knowledge_base(
                session,
                "第二个知识库",
            )

            # 两个知识库保存内容哈希相同的文档。
            first_document = await create_document(
                session,
                first_kb.id,
            )
            second_document = await create_document(
                session,
                second_kb.id,
                name="相同内容.pdf",
                file_path="uploads/test/same_content.pdf",
            )

            await session.commit()

            assert first_document.id is not None
            assert second_document.id is not None
            assert first_document.content_hash == second_document.content_hash
            assert first_document.knowledge_base_id != second_document.knowledge_base_id

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "invalid_data",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 256},
        {"file_size": -1},
        {"content_hash": "a" * 63},
        {"content_hash": "a" * 65},
        {"status": "unknown"},
    ],
    ids=[
        "empty-name",
        "whitespace-name",
        "name-too-long",
        "negative-file-size",
        "hash-too-short",
        "hash-too-long",
        "invalid-status",
    ],
)
def test_document_rejects_invalid_data(database, invalid_data: dict):
    """测试数据库拒绝不符合约束的文档数据。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)

            await create_document(
                session,
                knowledge_base.id,
                **invalid_data,
            )

            with pytest.raises(IntegrityError):
                await session.commit()

            await session.rollback()

    asyncio.run(run_test())


def test_document_rejects_nonexistent_knowledge_base(database):
    """测试数据库拒绝引用不存在知识库的文档。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            await create_document(
                session,
                knowledge_base_id=99999,
            )

            with pytest.raises(IntegrityError):
                await session.commit()

            await session.rollback()

    asyncio.run(run_test())


def test_deleting_knowledge_base_cascades_documents(database):
    """测试删除知识库时数据库级联删除关联文档。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)

            await create_document(
                session,
                knowledge_base.id,
            )
            await create_document(
                session,
                knowledge_base.id,
                name="第二份文档.pdf",
                file_path="uploads/test/document2.pdf",
                content_hash="b" * 64,
            )

            knowledge_base_id = knowledge_base.id

            await session.commit()

            result = await session.execute(
                select(Document).where(
                    Document.knowledge_base_id == knowledge_base_id,
                )
            )
            assert len(result.scalars().all()) == 2

            await session.delete(knowledge_base)
            await session.commit()

        # 使用新的 Session 验证数据库中的实际删除结果。
        async with session_factory() as session:
            result = await session.execute(
                select(Document).where(
                    Document.knowledge_base_id == knowledge_base_id,
                )
            )

            assert result.scalars().all() == []

            result = await session.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == knowledge_base_id,
                )
            )

            assert result.scalar_one_or_none() is None

    asyncio.run(run_test())
