"""KnowledgeFlow DocumentRepository 测试。"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect

from app.models import Document, DocumentChunk, KnowledgeBase
from app.repositories import DocumentRepository


async def create_test_document(
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


def test_repository_initializes_with_document_model(database):
    """测试 Repository 正确绑定 Document 模型。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentRepository(session)

            assert repository.session is session
            assert repository.model is Document

    asyncio.run(run_test())


def test_get_by_id_with_chunks_returns_document(database):
    """测试查询文档时能够预加载关联分块。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(name="分块测试知识库")
            session.add(knowledge_base)
            await session.flush()

            document = await create_test_document(
                session,
                knowledge_base.id,
            )

            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content="这是测试分块内容。",
                token_count=10,
                start_index=0,
                end_index=10,
            )
            session.add(chunk)
            await session.flush()

            repository = DocumentRepository(session)
            result = await repository.get_by_id_with_chunks(document.id)

            assert result is not None
            assert result.id == document.id
            assert len(result.chunks) == 1
            assert result.chunks[0].content == "这是测试分块内容。"
            assert "chunks" not in inspect(result).unloaded

    asyncio.run(run_test())


def test_get_by_id_with_chunks_returns_empty_chunks(database):
    """测试没有分块的文档也能正常查询。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(name="空分块知识库")
            session.add(knowledge_base)
            await session.flush()

            document = await create_test_document(
                session,
                knowledge_base.id,
            )

            repository = DocumentRepository(session)
            result = await repository.get_by_id_with_chunks(document.id)

            assert result is not None
            assert result.chunks == []

    asyncio.run(run_test())


def test_get_by_id_with_chunks_returns_none_when_not_found(database):
    """测试查询不存在的文档时返回 None。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentRepository(session)

            result = await repository.get_by_id_with_chunks(999)

            assert result is None

    asyncio.run(run_test())


def test_get_by_content_hash_returns_document(database):
    """测试根据知识库 ID 和内容哈希查询文档。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(name="哈希查询知识库")
            session.add(knowledge_base)
            await session.flush()

            content_hash = "b" * 64
            document = await create_test_document(
                session,
                knowledge_base.id,
                content_hash=content_hash,
            )

            repository = DocumentRepository(session)
            result = await repository.get_by_content_hash(
                knowledge_base.id,
                content_hash,
            )

            assert result is not None
            assert result.id == document.id

    asyncio.run(run_test())


def test_get_by_content_hash_is_scoped_to_knowledge_base(database):
    """测试相同哈希在不同知识库中独立查询。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            first_kb = KnowledgeBase(name="第一个知识库")
            second_kb = KnowledgeBase(name="第二个知识库")
            session.add_all([first_kb, second_kb])
            await session.flush()

            content_hash = "c" * 64

            first_document = await create_test_document(
                session,
                first_kb.id,
                content_hash=content_hash,
            )
            second_document = await create_test_document(
                session,
                second_kb.id,
                content_hash=content_hash,
                name="第二份相同内容.pdf",
            )

            repository = DocumentRepository(session)

            first_result = await repository.get_by_content_hash(
                first_kb.id,
                content_hash,
            )
            second_result = await repository.get_by_content_hash(
                second_kb.id,
                content_hash,
            )

            assert first_result.id == first_document.id
            assert second_result.id == second_document.id
            assert first_result.id != second_result.id

    asyncio.run(run_test())


def test_get_by_content_hash_returns_none_when_not_found(database):
    """测试查询不存在的内容哈希时返回 None。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentRepository(session)

            result = await repository.get_by_content_hash(
                999,
                "d" * 64,
            )

            assert result is None

    asyncio.run(run_test())


def test_get_by_content_hash_rejects_invalid_hash(database):
    """测试内容哈希长度不正确时拒绝查询。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentRepository(session)

            with pytest.raises(ValueError, match="长度必须为 64"):
                await repository.get_by_content_hash(1, "invalid")

    asyncio.run(run_test())


def test_get_by_content_hash_rejects_non_string_hash(database):
    """测试内容哈希不是字符串时拒绝查询。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentRepository(session)

            with pytest.raises(TypeError, match="必须是字符串"):
                await repository.get_by_content_hash(1, None)

    asyncio.run(run_test())


def test_get_by_knowledge_base_returns_documents(database):
    """测试查询指定知识库下的全部文档。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            first_kb = KnowledgeBase(name="第一个知识库")
            second_kb = KnowledgeBase(name="第二个知识库")
            session.add_all([first_kb, second_kb])
            await session.flush()

            await create_test_document(session, first_kb.id)
            await create_test_document(
                session,
                first_kb.id,
                name="第二份文档.pdf",
                content_hash="e" * 64,
            )
            await create_test_document(
                session,
                second_kb.id,
                name="其他知识库文档.pdf",
            )

            repository = DocumentRepository(session)
            result = await repository.get_by_knowledge_base(first_kb.id)

            assert len(result) == 2
            assert all(item.knowledge_base_id == first_kb.id for item in result)

    asyncio.run(run_test())


def test_get_by_knowledge_base_supports_pagination(database):
    """测试按知识库查询支持稳定分页。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(name="分页测试知识库")
            session.add(knowledge_base)
            await session.flush()

            for index in range(3):
                await create_test_document(
                    session,
                    knowledge_base.id,
                    name=f"文档{index}.pdf",
                    content_hash=str(index) * 64,
                )

            repository = DocumentRepository(session)

            first_page = await repository.get_by_knowledge_base(
                knowledge_base.id,
                offset=0,
                limit=2,
            )
            second_page = await repository.get_by_knowledge_base(
                knowledge_base.id,
                offset=2,
                limit=2,
            )

            assert len(first_page) == 2
            assert len(second_page) == 1
            assert first_page[0].id < first_page[1].id
            assert first_page[1].id < second_page[0].id

    asyncio.run(run_test())


def test_get_by_knowledge_base_returns_empty_for_unknown_id(database):
    """测试查询不存在的知识库时返回空列表。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentRepository(session)

            result = await repository.get_by_knowledge_base(999)

            assert result == []

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("offset", "limit", "message"),
    [
        (-1, 10, "offset 不能小于 0"),
        (0, 0, "limit 必须大于 0"),
        (0, -1, "limit 必须大于 0"),
    ],
)
def test_get_by_knowledge_base_rejects_invalid_pagination(
    database,
    offset,
    limit,
    message,
):
    """测试知识库文档查询拒绝非法分页参数。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentRepository(session)

            with pytest.raises(ValueError, match=message):
                await repository.get_by_knowledge_base(
                    1,
                    offset=offset,
                    limit=limit,
                )

    asyncio.run(run_test())


def test_get_by_status_returns_matching_documents(database):
    """测试根据处理状态查询文档。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(name="状态查询知识库")
            session.add(knowledge_base)
            await session.flush()

            await create_test_document(
                session,
                knowledge_base.id,
                status="pending",
            )
            await create_test_document(
                session,
                knowledge_base.id,
                name="已完成文档.pdf",
                content_hash="f" * 64,
                status="completed",
            )
            await create_test_document(
                session,
                knowledge_base.id,
                name="失败文档.pdf",
                content_hash="1" * 64,
                status="failed",
            )

            repository = DocumentRepository(session)
            result = await repository.get_by_status("pending")

            assert len(result) == 1
            assert result[0].status == "pending"

    asyncio.run(run_test())


def test_get_by_status_supports_pagination(database):
    """测试按状态查询支持分页。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(name="状态分页知识库")
            session.add(knowledge_base)
            await session.flush()

            for index in range(3):
                await create_test_document(
                    session,
                    knowledge_base.id,
                    name=f"待处理文档{index}.pdf",
                    content_hash=str(index + 2) * 64,
                    status="pending",
                )

            repository = DocumentRepository(session)

            first_page = await repository.get_by_status(
                "pending",
                offset=0,
                limit=2,
            )
            second_page = await repository.get_by_status(
                "pending",
                offset=2,
                limit=2,
            )

            assert len(first_page) == 2
            assert len(second_page) == 1
            assert first_page[0].id < first_page[1].id
            assert first_page[1].id < second_page[0].id

    asyncio.run(run_test())


def test_get_by_status_rejects_unknown_status(database):
    """测试拒绝不支持的文档状态。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentRepository(session)

            with pytest.raises(ValueError, match="不支持的文档状态"):
                await repository.get_by_status("unknown")

    asyncio.run(run_test())


def test_get_by_status_rejects_non_string_status(database):
    """测试状态参数必须是字符串。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentRepository(session)

            with pytest.raises(TypeError, match="status 必须是字符串"):
                await repository.get_by_status(None)

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("offset", "limit", "message"),
    [
        (-1, 10, "offset 不能小于 0"),
        (0, 0, "limit 必须大于 0"),
        (0, -1, "limit 必须大于 0"),
    ],
)
def test_get_by_status_rejects_invalid_pagination(
    database,
    offset,
    limit,
    message,
):
    """测试状态查询拒绝非法分页参数。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentRepository(session)

            with pytest.raises(ValueError, match=message):
                await repository.get_by_status(
                    "pending",
                    offset=offset,
                    limit=limit,
                )

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("status", "is_stale", "expected"),
    [
        ("processing", True, True),
        ("processing", False, False),
        ("pending", True, False),
        ("completed", True, False),
        ("failed", True, False),
    ],
)
def test_claim_stale_processing_filters_status_and_time(
    database,
    status,
    is_stale,
    expected,
):
    """测试原子认领正确过滤状态和更新时间。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(name="原子认领测试知识库")
            session.add(knowledge_base)
            await session.flush()

            old_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
            recent_time = datetime.now(UTC).replace(tzinfo=None)

            document = await create_test_document(
                session,
                knowledge_base.id,
                status=status,
                updated_at=old_time if is_stale else recent_time,
            )
            await session.commit()

            repository = DocumentRepository(session)
            threshold = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=30)

            result = await repository.claim_stale_processing(
                document.id,
                threshold,
            )

            assert result is expected

            await session.rollback()

    asyncio.run(run_test())


def test_claim_stale_processing_rejects_repeated_claim(database):
    """测试同一文档成功认领后不能再次认领。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(name="重复认领测试知识库")
            session.add(knowledge_base)
            await session.flush()

            document = await create_test_document(
                session,
                knowledge_base.id,
                status="processing",
                updated_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
            )
            await session.commit()

            repository = DocumentRepository(session)
            threshold = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=30)

            first_result = await repository.claim_stale_processing(
                document.id,
                threshold,
            )
            second_result = await repository.claim_stale_processing(
                document.id,
                threshold,
            )

            assert first_result is True
            assert second_result is False

            await session.rollback()

    asyncio.run(run_test())


def test_claim_stale_processing_does_not_commit(database):
    """测试原子认领不会自动提交事务。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = KnowledgeBase(name="事务边界测试知识库")
            session.add(knowledge_base)
            await session.flush()

            document = await create_test_document(
                session,
                knowledge_base.id,
                status="processing",
                updated_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
            )
            await session.commit()

            # 在事务回滚和 Session 关闭前保存主键
            document_id = document.id

            repository = DocumentRepository(session)
            threshold = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=30)

            result = await repository.claim_stale_processing(
                document_id,
                threshold,
            )

            assert result is True

            await session.rollback()

        async with session_factory() as verification_session:
            persisted_document = await verification_session.get(
                Document,
                document_id,
            )

            assert persisted_document is not None
            assert persisted_document.updated_at < threshold

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("document_id", "updated_before", "error_type", "message"),
    [
        (True, datetime(2026, 1, 1), TypeError, "document_id"),
        (0, datetime(2026, 1, 1), ValueError, "document_id"),
        (1, "2026-01-01", TypeError, "datetime"),
        (1, datetime(2026, 1, 1).astimezone(), ValueError, "无时区"),
    ],
)
def test_claim_stale_processing_rejects_invalid_arguments(
    database,
    document_id,
    updated_before,
    error_type,
    message,
):
    """测试原子认领拒绝非法参数。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = DocumentRepository(session)

            with pytest.raises(error_type, match=message):
                await repository.claim_stale_processing(
                    document_id,
                    updated_before,
                )

    asyncio.run(run_test())
