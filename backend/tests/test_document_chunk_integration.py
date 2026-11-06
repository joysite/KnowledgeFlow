"""KnowledgeFlow DocumentChunk SQLite 集成测试。"""

import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.models import Document, DocumentChunk, KnowledgeBase


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
    await session.flush()

    return document


async def create_document_chunk(
    session,
    document_id: int,
    **kwargs,
) -> DocumentChunk:
    """创建测试文档分块。"""
    chunk_data = {
        "document_id": document_id,
        "chunk_index": 0,
        "content": "这是一个测试文档分块。",
        "token_count": 10,
        "start_index": 0,
        "end_index": 12,
    }
    chunk_data.update(kwargs)

    chunk = DocumentChunk(**chunk_data)
    session.add(chunk)

    return chunk


def test_document_chunk_can_be_created_and_queried(database):
    """测试文档分块能够成功插入和查询。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            document = await create_document(
                session,
                knowledge_base.id,
            )

            chunk = await create_document_chunk(
                session,
                document.id,
            )

            await session.commit()
            await session.refresh(chunk)

            assert chunk.id is not None
            assert chunk.document_id == document.id
            assert chunk.chunk_index == 0
            assert chunk.content == "这是一个测试文档分块。"
            assert chunk.token_count == 10
            assert chunk.start_index == 0
            assert chunk.end_index == 12
            assert chunk.created_at is not None

            result = await session.execute(
                select(DocumentChunk).where(
                    DocumentChunk.id == chunk.id,
                )
            )
            queried_chunk = result.scalar_one()

            assert queried_chunk.content == chunk.content
            assert queried_chunk.document_id == document.id

    asyncio.run(run_test())


def test_document_chunk_metadata_round_trip_and_default_is_independent(database):
    """测试 JSON 元数据往返和默认字典相互独立。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            document = await create_document(
                session,
                knowledge_base.id,
            )

            # 显式设置嵌套 JSON 元数据。
            custom_metadata = {
                "source": "pdf",
                "page": 3,
                "tags": ["AI", "RAG"],
                "extra": {
                    "language": "zh-CN",
                },
            }

            custom_chunk = await create_document_chunk(
                session,
                document.id,
                chunk_index=0,
                chunk_metadata=custom_metadata,
            )

            # 不传入元数据，验证默认字典。
            first_default_chunk = await create_document_chunk(
                session,
                document.id,
                chunk_index=1,
                content="第二个测试分块。",
                start_index=12,
                end_index=21,
            )

            second_default_chunk = await create_document_chunk(
                session,
                document.id,
                chunk_index=2,
                content="第三个测试分块。",
                start_index=21,
                end_index=30,
            )

            await session.flush()

            assert first_default_chunk.chunk_metadata == {}
            assert second_default_chunk.chunk_metadata == {}

            # 两个默认字典不能是同一个对象。
            assert first_default_chunk.chunk_metadata is not second_default_chunk.chunk_metadata

            # 修改其中一个默认字典，不应影响另一个。
            first_default_chunk.chunk_metadata["test"] = "独立字典"

            assert second_default_chunk.chunk_metadata == {}

            await session.commit()

            custom_chunk_id = custom_chunk.id
            first_default_chunk_id = first_default_chunk.id

        # 使用新的 Session 验证数据库 JSON 持久化结果。
        async with session_factory() as session:
            result = await session.execute(
                select(DocumentChunk).where(
                    DocumentChunk.id == custom_chunk_id,
                )
            )
            queried_custom_chunk = result.scalar_one()

            assert queried_custom_chunk.chunk_metadata == custom_metadata

            result = await session.execute(
                select(DocumentChunk).where(
                    DocumentChunk.id == first_default_chunk_id,
                )
            )
            queried_default_chunk = result.scalar_one()

            assert queried_default_chunk.chunk_metadata == {
                "test": "独立字典",
            }

    asyncio.run(run_test())


def test_document_chunk_bidirectional_relationship(database):
    """测试 Document 与 DocumentChunk 双向关系。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            document = await create_document(
                session,
                knowledge_base.id,
            )

            chunk = await create_document_chunk(
                session,
                document.id,
            )

            await session.commit()

            document_id = document.id
            chunk_id = chunk.id

            # 查询 Document，并预加载关联分块。
            result = await session.execute(
                select(Document)
                .options(selectinload(Document.chunks))
                .where(Document.id == document_id)
            )
            queried_document = result.scalar_one()

            assert len(queried_document.chunks) == 1
            assert queried_document.chunks[0].id == chunk_id

            # 查询 DocumentChunk，并预加载所属文档。
            result = await session.execute(
                select(DocumentChunk)
                .options(selectinload(DocumentChunk.document))
                .where(DocumentChunk.id == chunk_id)
            )
            queried_chunk = result.scalar_one()

            assert queried_chunk.document.id == document_id

    asyncio.run(run_test())


def test_document_chunk_duplicate_index_is_rejected(database):
    """测试同一文档不允许存在重复分块序号。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            document = await create_document(
                session,
                knowledge_base.id,
            )

            # 第一条分块正常写入。
            await create_document_chunk(
                session,
                document.id,
                chunk_index=0,
            )
            await session.commit()

            # 第二条分块使用相同序号。
            await create_document_chunk(
                session,
                document.id,
                chunk_index=0,
                content="重复序号分块。",
            )

            with pytest.raises(IntegrityError):
                await session.commit()

            await session.rollback()

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "invalid_data",
    [
        {"chunk_index": -1},
        {"content": ""},
        {"content": "   "},
        {"token_count": -1},
        {"start_index": -1},
        {"start_index": 10, "end_index": 10},
        {"start_index": 10, "end_index": 9},
    ],
    ids=[
        "negative-chunk-index",
        "empty-content",
        "whitespace-content",
        "negative-token-count",
        "negative-start-index",
        "empty-index-range",
        "reversed-index-range",
    ],
)
def test_document_chunk_rejects_invalid_data(database, invalid_data: dict):
    """测试数据库拒绝不符合约束的分块数据。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            document = await create_document(
                session,
                knowledge_base.id,
            )

            await create_document_chunk(
                session,
                document.id,
                **invalid_data,
            )

            with pytest.raises(IntegrityError):
                await session.commit()

            await session.rollback()

    asyncio.run(run_test())


def test_document_chunk_rejects_nonexistent_document(database):
    """测试数据库拒绝引用不存在文档的分块。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            await create_document_chunk(
                session,
                document_id=99999,
            )

            with pytest.raises(IntegrityError):
                await session.commit()

            await session.rollback()

    asyncio.run(run_test())


def test_deleting_document_cascades_document_chunks(database):
    """测试删除文档时数据库级联删除关联分块。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            document = await create_document(
                session,
                knowledge_base.id,
            )

            document_id = document.id

            await create_document_chunk(
                session,
                document_id,
                chunk_index=0,
            )
            await create_document_chunk(
                session,
                document_id,
                chunk_index=1,
                content="第二个测试分块。",
                start_index=12,
                end_index=21,
            )

            await session.commit()

            await session.delete(document)
            await session.commit()

        # 新 Session 验证数据库实际删除结果。
        async with session_factory() as session:
            result = await session.execute(
                select(DocumentChunk).where(
                    DocumentChunk.document_id == document_id,
                )
            )

            assert result.scalars().all() == []

            result = await session.execute(
                select(Document).where(
                    Document.id == document_id,
                )
            )

            assert result.scalar_one_or_none() is None

    asyncio.run(run_test())


def test_deleting_knowledge_base_cascades_documents_and_chunks(database):
    """测试删除知识库时级联删除文档及其分块。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            knowledge_base_id = knowledge_base.id

            document = await create_document(
                session,
                knowledge_base_id,
            )
            document_id = document.id

            await create_document_chunk(
                session,
                document_id,
                chunk_index=0,
            )
            await create_document_chunk(
                session,
                document_id,
                chunk_index=1,
                content="第二个测试分块。",
                start_index=12,
                end_index=21,
            )

            await session.commit()

            await session.delete(knowledge_base)
            await session.commit()

        # 使用新 Session 验证三层数据全部删除。
        async with session_factory() as session:
            result = await session.execute(
                select(DocumentChunk).where(
                    DocumentChunk.document_id == document_id,
                )
            )
            assert result.scalars().all() == []

            result = await session.execute(
                select(Document).where(
                    Document.id == document_id,
                )
            )
            assert result.scalar_one_or_none() is None

            result = await session.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == knowledge_base_id,
                )
            )
            assert result.scalar_one_or_none() is None

    asyncio.run(run_test())
