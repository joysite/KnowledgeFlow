"""KnowledgeFlow DocumentChunkRepository 单元及 SQLite 集成测试。"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.models import Document, DocumentChunk, KnowledgeBase
from app.repositories import DocumentChunkRepository


async def create_document(
    session,
    knowledge_base_name: str = "测试知识库",
    document_name: str = "测试文档.pdf",
) -> Document:
    """创建测试文档。"""
    knowledge_base = KnowledgeBase(name=knowledge_base_name)
    session.add(knowledge_base)
    await session.flush()

    document = Document(
        knowledge_base_id=knowledge_base.id,
        name=document_name,
        file_type="pdf",
        file_path=f"uploads/{document_name}",
        file_size=1024,
        content_hash="a" * 64,
    )
    session.add(document)
    await session.flush()

    return document


async def create_chunk(
    session,
    document_id: int,
    chunk_index: int,
    **kwargs,
) -> DocumentChunk:
    """创建测试分块。"""
    chunk_data = {
        "document_id": document_id,
        "chunk_index": chunk_index,
        "content": f"测试分块内容 {chunk_index}",
        "token_count": 10,
        "start_index": chunk_index * 10,
        "end_index": chunk_index * 10 + 10,
    }
    chunk_data.update(kwargs)

    chunk = DocumentChunk(**chunk_data)
    session.add(chunk)
    await session.flush()

    return chunk


def test_repository_initializes_with_document_chunk_model(database):
    """测试 Repository 正确初始化。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentChunkRepository(session)

            assert repository.model is DocumentChunk

    asyncio.run(run_test())


def test_get_by_document_returns_chunks_in_index_order(database):
    """测试查询结果按照分块序号升序排列。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            document = await create_document(session)

            await create_chunk(session, document.id, 2)
            await create_chunk(session, document.id, 0)
            await create_chunk(session, document.id, 1)

            repository = DocumentChunkRepository(session)
            result = await repository.get_by_document(document.id)

            assert [chunk.chunk_index for chunk in result] == [0, 1, 2]
            assert all(chunk.document_id == document.id for chunk in result)

    asyncio.run(run_test())


def test_get_by_document_returns_empty_list_when_no_chunks(database):
    """测试文档没有分块时返回空列表。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            document = await create_document(session)
            repository = DocumentChunkRepository(session)

            result = await repository.get_by_document(document.id)

            assert result == []

    asyncio.run(run_test())


def test_get_by_document_returns_empty_list_for_unknown_document(database):
    """测试查询不存在的文档时返回空列表。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentChunkRepository(session)

            result = await repository.get_by_document(99999)

            assert result == []

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("offset", "limit", "expected_indexes"),
    [
        (0, 2, [0, 1]),
        (1, 2, [1, 2]),
        (2, 2, [2, 3]),
        (10, 2, []),
    ],
)
def test_get_by_document_supports_pagination(
    database,
    offset,
    limit,
    expected_indexes,
):
    """测试分块查询支持分页。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            document = await create_document(session)

            for index in range(4):
                await create_chunk(session, document.id, index)

            repository = DocumentChunkRepository(session)
            result = await repository.get_by_document(
                document.id,
                offset=offset,
                limit=limit,
            )

            assert [chunk.chunk_index for chunk in result] == expected_indexes

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("offset", "limit", "error_message"),
    [
        (-1, 10, "offset 不能小于 0"),
        (0, 0, "limit 必须大于 0"),
        (0, -1, "limit 必须大于 0"),
    ],
)
def test_get_by_document_rejects_invalid_pagination(
    database,
    offset,
    limit,
    error_message,
):
    """测试分块查询拒绝非法分页参数。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentChunkRepository(session)

            with pytest.raises(ValueError, match=error_message):
                await repository.get_by_document(
                    document_id=1,
                    offset=offset,
                    limit=limit,
                )

    asyncio.run(run_test())


def test_get_by_document_and_index_returns_matching_chunk(database):
    """测试根据文档 ID 和分块序号查询分块。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            document = await create_document(session)

            await create_chunk(session, document.id, 0)
            expected_chunk = await create_chunk(
                session,
                document.id,
                1,
                content="目标分块内容",
            )
            await create_chunk(session, document.id, 2)

            repository = DocumentChunkRepository(session)
            result = await repository.get_by_document_and_index(
                document.id,
                1,
            )

            assert result is not None
            assert result.id == expected_chunk.id
            assert result.content == "目标分块内容"

    asyncio.run(run_test())


def test_get_by_document_and_index_returns_none_when_not_found(database):
    """测试查询不存在的分块时返回 None。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            document = await create_document(session)
            repository = DocumentChunkRepository(session)

            result = await repository.get_by_document_and_index(
                document.id,
                999,
            )

            assert result is None

    asyncio.run(run_test())


def test_get_by_document_and_index_is_scoped_to_document(database):
    """测试相同分块序号在不同文档之间相互隔离。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            first_document = await create_document(
                session,
                document_name="文档一.pdf",
            )
            second_document = await create_document(
                session,
                document_name="文档二.pdf",
            )

            first_chunk = await create_chunk(
                session,
                first_document.id,
                0,
                content="第一个文档的分块",
            )
            second_chunk = await create_chunk(
                session,
                second_document.id,
                0,
                content="第二个文档的分块",
            )

            repository = DocumentChunkRepository(session)

            first_result = await repository.get_by_document_and_index(
                first_document.id,
                0,
            )
            second_result = await repository.get_by_document_and_index(
                second_document.id,
                0,
            )

            assert first_result is not None
            assert second_result is not None
            assert first_result.id == first_chunk.id
            assert second_result.id == second_chunk.id
            assert first_result.id != second_result.id

    asyncio.run(run_test())


def test_create_many_persists_multiple_chunks(database):
    """测试批量创建多个分块。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            document = await create_document(session)
            repository = DocumentChunkRepository(session)

            chunks = [
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=f"批量分块内容 {index}",
                    token_count=10,
                    start_index=index * 10,
                    end_index=index * 10 + 10,
                )
                for index in range(3)
            ]

            result = await repository.create_many(chunks)

            assert result == chunks
            assert all(chunk.id is not None for chunk in result)

            saved = await repository.get_by_document(document.id)

            assert len(saved) == 3
            assert [chunk.chunk_index for chunk in saved] == [0, 1, 2]

    asyncio.run(run_test())


def test_create_many_returns_empty_list(database):
    """测试批量创建空列表。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentChunkRepository(session)

            result = await repository.create_many([])

            assert result == []

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "entities",
    [
        None,
        (),
        "invalid",
        {"invalid": "data"},
    ],
)
def test_create_many_rejects_non_list(entities, database):
    """测试批量创建拒绝非列表输入。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentChunkRepository(session)

            with pytest.raises(TypeError, match="entities 必须是列表"):
                await repository.create_many(entities)

    asyncio.run(run_test())


def test_create_many_rejects_invalid_element_without_partial_add(database):
    """测试批量创建遇到非法元素时不会部分添加数据。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            document = await create_document(session)
            repository = DocumentChunkRepository(session)

            valid_chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content="合法分块",
                token_count=5,
                start_index=0,
                end_index=4,
            )

            with pytest.raises(TypeError, match="元素必须是 DocumentChunk"):
                await repository.create_many([valid_chunk, object()])

            assert valid_chunk not in session

    asyncio.run(run_test())


def test_create_many_calls_flush_only_once(database, monkeypatch):
    """测试批量创建多个分块时只执行一次 flush。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            document = await create_document(session)
            repository = DocumentChunkRepository(session)

            chunks = [
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=f"批量分块内容 {index}",
                    token_count=10,
                    start_index=index * 10,
                    end_index=index * 10 + 10,
                )
                for index in range(3)
            ]

            # 只统计批量创建阶段的 flush 调用。
            flush_spy = AsyncMock(wraps=session.flush)
            monkeypatch.setattr(session, "flush", flush_spy)

            await repository.create_many(chunks)

            assert flush_spy.await_count == 1

    asyncio.run(run_test())


def test_get_by_ids_filters_knowledge_base_and_document_status(database):
    """验证批量查询只返回指定知识库中已完成文档的分块。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            first = await create_document(session)
            first.status = "completed"

            second = Document(
                knowledge_base_id=first.knowledge_base_id,
                name="处理中.pdf",
                file_type="pdf",
                file_path="uploads/处理中.pdf",
                file_size=100,
                content_hash="b" * 64,
                status="processing",
            )
            other_kb = KnowledgeBase(name="另一个知识库")
            session.add_all([second, other_kb])
            await session.flush()

            third = Document(
                knowledge_base_id=other_kb.id,
                name="其他知识库.pdf",
                file_type="pdf",
                file_path="uploads/其他知识库.pdf",
                file_size=100,
                content_hash="c" * 64,
                status="completed",
            )
            session.add(third)
            await session.flush()

            expected = await create_chunk(session, first.id, 0)
            processing = await create_chunk(session, second.id, 0)
            other = await create_chunk(session, third.id, 0)

            repository = DocumentChunkRepository(session)
            result = await repository.get_by_ids(
                first.knowledge_base_id,
                [other.id, processing.id, expected.id],
            )

            assert [chunk.id for chunk in result] == [expected.id]

    asyncio.run(run_test())


def test_get_by_ids_returns_empty_list_when_no_match(database):
    """验证没有匹配分块时返回空列表。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentChunkRepository(session)

            result = await repository.get_by_ids(1, [99999])

            assert result == []

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("knowledge_base_id", "chunk_ids", "error"),
    [
        (True, [1], TypeError),
        (0, [1], ValueError),
        (1, [], ValueError),
        (1, [True], TypeError),
        (1, [0], ValueError),
        (1, [1, 1], ValueError),
    ],
)
def test_get_by_ids_rejects_invalid_input(
    database,
    knowledge_base_id,
    chunk_ids,
    error,
):
    """验证批量查询拒绝非法参数。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentChunkRepository(session)

            with pytest.raises(error):
                await repository.get_by_ids(knowledge_base_id, chunk_ids)

    asyncio.run(run_test())


def test_get_by_knowledge_base_filters_status_and_knowledge_base(database):
    """验证只查询指定知识库中已完成文档的分块。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            completed = await create_document(session, document_name="已完成.pdf")
            completed.status = "completed"

            processing = await create_document(session, document_name="处理中.pdf")
            processing.status = "processing"

            other_kb = KnowledgeBase(name="其他知识库")
            session.add(other_kb)
            await session.flush()

            other_document = Document(
                knowledge_base_id=other_kb.id,
                name="其他文档.pdf",
                file_type="pdf",
                file_path="uploads/其他文档.pdf",
                file_size=100,
                content_hash="d" * 64,
                status="completed",
            )
            session.add(other_document)
            await session.flush()

            expected = await create_chunk(session, completed.id, 0)
            await create_chunk(session, processing.id, 0)
            await create_chunk(session, other_document.id, 0)

            repository = DocumentChunkRepository(session)
            result = await repository.get_by_knowledge_base(completed.knowledge_base_id)

            assert [chunk.id for chunk in result] == [expected.id]
            assert result[0].document.name == "已完成.pdf"

    asyncio.run(run_test())


def test_get_by_knowledge_base_orders_and_paginates(database):
    """验证跨文档查询按文档和分块顺序排列，并支持分页。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            first = await create_document(session, document_name="文档一.pdf")
            second = Document(
                knowledge_base_id=first.knowledge_base_id,
                name="文档二.pdf",
                file_type="pdf",
                file_path="uploads/文档二.pdf",
                file_size=1024,
                content_hash="e" * 64,
                status="completed",
            )
            session.add(second)
            await session.flush()
            first.status = "completed"

            await create_chunk(session, second.id, 1)
            await create_chunk(session, first.id, 1)
            await create_chunk(session, first.id, 0)
            await create_chunk(session, second.id, 0)

            repository = DocumentChunkRepository(session)
            all_chunks = await repository.get_by_knowledge_base(first.knowledge_base_id)
            page = await repository.get_by_knowledge_base(
                first.knowledge_base_id,
                offset=1,
                limit=2,
            )

            assert [(chunk.document_id, chunk.chunk_index) for chunk in all_chunks] == [
                (first.id, 0),
                (first.id, 1),
                (second.id, 0),
                (second.id, 1),
            ]
            assert [chunk.id for chunk in page] == [chunk.id for chunk in all_chunks[1:3]]
            assert all(chunk.document is not None for chunk in all_chunks)

    asyncio.run(run_test())


def test_get_by_knowledge_base_returns_empty_list_when_no_match(database):
    """验证没有已完成文档分块时返回空列表。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            document = await create_document(session)
            repository = DocumentChunkRepository(session)

            result = await repository.get_by_knowledge_base(document.knowledge_base_id)

            assert result == []

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("knowledge_base_id", "offset", "limit", "error"),
    [
        (True, 0, 10, TypeError),
        (0, 0, 10, ValueError),
        (1, -1, 10, ValueError),
        (1, 0, 0, ValueError),
    ],
)
def test_get_by_knowledge_base_rejects_invalid_input(
    database,
    knowledge_base_id,
    offset,
    limit,
    error,
):
    """验证知识库分块查询拒绝非法参数。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentChunkRepository(session)

            with pytest.raises(error):
                await repository.get_by_knowledge_base(
                    knowledge_base_id,
                    offset=offset,
                    limit=limit,
                )

    asyncio.run(run_test())
