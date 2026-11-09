"""KnowledgeFlow DocumentService 测试。"""

import asyncio

import pytest
from sqlalchemy import func, select

from app.models import Document, DocumentChunk, KnowledgeBase
from app.services import DocumentService

HASH_A = "a" * 64
HASH_B = "b" * 64


async def create_knowledge_base(session, name="测试知识库"):
    """创建测试知识库。"""
    knowledge_base = KnowledgeBase(name=name)
    session.add(knowledge_base)
    await session.flush()
    return knowledge_base


async def create_document(session, knowledge_base_id, **kwargs):
    """创建测试文档。"""
    data = {
        "knowledge_base_id": knowledge_base_id,
        "name": "测试文档.pdf",
        "file_type": "pdf",
        "file_path": "uploads/test.pdf",
        "file_size": 1024,
        "content_hash": HASH_A,
    }
    data.update(kwargs)
    document = Document(**data)
    session.add(document)
    await session.flush()
    return document


def test_service_initializes_with_session(database):
    """测试 Service 初始化。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = DocumentService(session)
            assert service.session is session
            assert service.repository.session is session
            assert service.knowledge_base_repository.session is session

    asyncio.run(run_test())


def test_create_document(database):
    """测试创建文档并规范化输入。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            service = DocumentService(session)

            result = await service.create(
                kb.id,
                "  Python 教程.PDF  ",
                " PDF ",
                " uploads/python.pdf ",
                2048,
                HASH_A.upper(),
            )

            assert result.id is not None
            assert result.name == "Python 教程.PDF"
            assert result.file_type == "pdf"
            assert result.file_path == "uploads/python.pdf"
            assert result.file_size == 2048
            assert result.content_hash == HASH_A
            assert result.status == "pending"

        async with session_factory() as session:
            saved = await session.get(Document, result.id)
            assert saved is not None
            assert saved.name == "Python 教程.PDF"

    asyncio.run(run_test())


def test_create_rejects_unknown_knowledge_base(database):
    """测试创建时拒绝不存在的知识库。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = DocumentService(session)

            with pytest.raises(ValueError, match="知识库不存在"):
                await service.create(999, "test.pdf", "pdf", "uploads/test.pdf", 100, HASH_A)

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("name", "error"),
    [
        ("", "文档名称不能为空"),
        ("   ", "文档名称不能为空"),
        ("x" * 256, "不能超过 255"),
    ],
)
def test_create_rejects_invalid_name(database, name, error):
    """测试文档名称校验。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            service = DocumentService(session)

            with pytest.raises(ValueError, match=error):
                await service.create(kb.id, name, "pdf", "uploads/test.pdf", 100, HASH_A)

    asyncio.run(run_test())


def test_create_rejects_non_string_name(database):
    """测试拒绝非字符串名称。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            service = DocumentService(session)

            with pytest.raises(TypeError, match="name 必须是字符串"):
                await service.create(kb.id, None, "pdf", "uploads/test.pdf", 100, HASH_A)

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("file_type", "error"),
    [
        ("", "文件类型不能为空"),
        ("x" * 21, "不能超过 20"),
    ],
)
def test_create_rejects_invalid_file_type(database, file_type, error):
    """测试文件类型校验。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            service = DocumentService(session)

            with pytest.raises(ValueError, match=error):
                await service.create(kb.id, "test.pdf", file_type, "uploads/test.pdf", 100, HASH_A)

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("file_path", "error"),
    [
        ("", "文件路径不能为空"),
        ("   ", "文件路径不能为空"),
        ("x" * 1025, "不能超过 1024"),
    ],
)
def test_create_rejects_invalid_file_path(database, file_path, error):
    """测试文件路径校验。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            service = DocumentService(session)

            with pytest.raises(ValueError, match=error):
                await service.create(kb.id, "test.pdf", "pdf", file_path, 100, HASH_A)

    asyncio.run(run_test())


@pytest.mark.parametrize("file_size", [-1, 1.5, True, "100"])
def test_create_rejects_invalid_file_size(database, file_size):
    """测试拒绝非法文件大小。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            service = DocumentService(session)

            with pytest.raises((TypeError, ValueError)):
                await service.create(
                    kb.id, "test.pdf", "pdf", "uploads/test.pdf", file_size, HASH_A
                )

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "content_hash",
    ["invalid", "g" * 64, "a" * 63, "a" * 65],
)
def test_create_rejects_invalid_hash(database, content_hash):
    """测试拒绝非法 SHA-256 哈希。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            service = DocumentService(session)

            with pytest.raises(ValueError, match="64 位十六进制"):
                await service.create(
                    kb.id, "test.pdf", "pdf", "uploads/test.pdf", 100, content_hash
                )

    asyncio.run(run_test())


def test_create_rejects_duplicate_hash_in_same_knowledge_base(database):
    """测试同一知识库内拒绝重复文档。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            await create_document(session, kb.id)
            service = DocumentService(session)

            with pytest.raises(ValueError, match="已存在相同内容"):
                await service.create(
                    kb.id, "duplicate.pdf", "pdf", "uploads/duplicate.pdf", 100, HASH_A
                )

    asyncio.run(run_test())


def test_create_allows_same_hash_in_different_knowledge_bases(database):
    """测试不同知识库允许相同哈希。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            first = await create_knowledge_base(session, "第一个知识库")
            second = await create_knowledge_base(session, "第二个知识库")
            service = DocumentService(session)

            first_doc = await service.create(
                first.id, "first.pdf", "pdf", "uploads/first.pdf", 100, HASH_A
            )
            second_doc = await service.create(
                second.id, "second.pdf", "pdf", "uploads/second.pdf", 100, HASH_A
            )

            assert first_doc.id != second_doc.id

    asyncio.run(run_test())


def test_get_by_id_and_missing_document(database):
    """测试按 ID 查询及不存在的情况。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            document = await create_document(session, kb.id)
            service = DocumentService(session)

            result = await service.get_by_id(document.id)
            assert result is not None
            assert result.id == document.id
            assert await service.get_by_id(999) is None

    asyncio.run(run_test())


def test_get_by_id_with_chunks(database):
    """测试查询文档及其分块。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            document = await create_document(session, kb.id)
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=0,
                    content="测试分块内容",
                    token_count=5,
                    start_index=0,
                    end_index=6,
                )
            )
            await session.flush()

            service = DocumentService(session)
            result = await service.get_by_id_with_chunks(document.id)

            assert result is not None
            assert len(result.chunks) == 1
            assert result.chunks[0].content == "测试分块内容"
            assert await service.get_by_id_with_chunks(999) is None

    asyncio.run(run_test())


def test_get_by_content_hash(database):
    """测试按知识库和哈希查询文档。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            document = await create_document(session, kb.id)
            service = DocumentService(session)

            result = await service.get_by_content_hash(kb.id, HASH_A.upper())

            assert result is not None
            assert result.id == document.id
            assert await service.get_by_content_hash(kb.id, HASH_B) is None

    asyncio.run(run_test())


def test_get_by_knowledge_base_supports_pagination(database):
    """测试按知识库分页查询。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)

            for index in range(3):
                await create_document(
                    session,
                    kb.id,
                    name=f"文档{index}.pdf",
                    content_hash=str(index) * 64,
                )

            service = DocumentService(session)
            first = await service.get_by_knowledge_base(kb.id, 0, 2)
            second = await service.get_by_knowledge_base(kb.id, 2, 2)

            assert len(first) == 2
            assert len(second) == 1

    asyncio.run(run_test())


def test_get_by_status(database):
    """测试按处理状态查询。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            await create_document(session, kb.id, status="pending")
            await create_document(session, kb.id, status="completed", content_hash=HASH_B)

            service = DocumentService(session)
            result = await service.get_by_status("pending")

            assert len(result) == 1
            assert result[0].status == "pending"

    asyncio.run(run_test())


def test_update_document_metadata(database):
    """测试更新文档元数据。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            document = await create_document(session, kb.id)
            service = DocumentService(session)

            result = await service.update(
                document.id,
                {
                    "name": " 新名称.md ",
                    "file_type": " MD ",
                    "file_path": " uploads/new.md ",
                    "file_size": 2048,
                },
            )

            assert result is not None
            assert result.name == "新名称.md"
            assert result.file_type == "md"
            assert result.file_path == "uploads/new.md"
            assert result.file_size == 2048

    asyncio.run(run_test())


def test_update_missing_document(database):
    """测试更新不存在的文档。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = DocumentService(session)
            assert await service.update(999, {"name": "新名称"}) is None

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"id": 1},
        {"knowledge_base_id": 2},
        {"content_hash": HASH_B},
        {"status": "completed"},
        {"error_message": "错误"},
        {"unknown": "value"},
    ],
)
def test_update_rejects_protected_or_invalid_fields(database, data):
    """测试更新时拒绝受保护字段和空数据。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = DocumentService(session)

            with pytest.raises(ValueError):
                await service.update(1, data)

    asyncio.run(run_test())


def test_update_rejects_non_dict(database):
    """测试更新时拒绝非字典数据。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = DocumentService(session)

            with pytest.raises(TypeError, match="data 必须是字典"):
                await service.update(1, None)

    asyncio.run(run_test())


def test_update_validation_does_not_partially_modify(database):
    """测试非法更新数据不会产生部分修改。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            document = await create_document(session, kb.id)
            service = DocumentService(session)

            with pytest.raises(ValueError, match="文档名称不能为空"):
                await service.update(
                    document.id,
                    {"name": "   ", "file_path": "uploads/changed.pdf"},
                )

            assert document.name == "测试文档.pdf"
            assert document.file_path == "uploads/test.pdf"

    asyncio.run(run_test())


def test_update_status_to_failed(database):
    """测试更新失败状态及错误信息。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            document = await create_document(session, kb.id)
            service = DocumentService(session)

            result = await service.update_status(document.id, "failed", " PDF 解析失败 ")

            assert result is not None
            assert result.status == "failed"
            assert result.error_message == "PDF 解析失败"

    asyncio.run(run_test())


def test_update_status_clears_old_error(database):
    """测试非失败状态自动清除旧错误信息。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            document = await create_document(
                session, kb.id, status="failed", error_message="旧错误"
            )
            service = DocumentService(session)

            result = await service.update_status(document.id, "processing")

            assert result is not None
            assert result.status == "processing"
            assert result.error_message is None

    asyncio.run(run_test())


def test_update_status_rejects_failed_without_error(database):
    """测试 failed 状态必须提供错误信息。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = DocumentService(session)

            with pytest.raises(ValueError, match="必须提供 error_message"):
                await service.update_status(1, "failed")

    asyncio.run(run_test())


def test_update_status_rejects_invalid_status(database):
    """测试拒绝不支持的状态。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = DocumentService(session)

            with pytest.raises(ValueError, match="不支持的文档状态"):
                await service.update_status(1, "unknown")

    asyncio.run(run_test())


def test_update_status_missing_document(database):
    """测试更新不存在文档的状态。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = DocumentService(session)
            assert await service.update_status(999, "pending") is None

    asyncio.run(run_test())


def test_delete_document_cascades_chunks(database):
    """测试删除文档时级联删除分块元数据。"""
    engine, session_factory = database

    async def run_test():
        async with engine.begin() as connection:
            await connection.exec_driver_sql("PRAGMA foreign_keys=ON")

        async with session_factory() as session:
            kb = await create_knowledge_base(session)
            document = await create_document(session, kb.id)
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content="需要删除的分块",
                token_count=5,
                start_index=0,
                end_index=7,
            )
            session.add(chunk)
            await session.flush()

            document_id = document.id
            chunk_id = chunk.id

            service = DocumentService(session)
            assert await service.delete(document_id) is True

        async with session_factory() as session:
            document_count = await session.scalar(
                select(func.count()).select_from(Document).where(Document.id == document_id)
            )
            chunk_count = await session.scalar(
                select(func.count()).select_from(DocumentChunk).where(DocumentChunk.id == chunk_id)
            )

            assert document_count == 0
            assert chunk_count == 0

    asyncio.run(run_test())


def test_delete_returns_false_when_missing(database):
    """测试删除不存在的文档。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = DocumentService(session)
            assert await service.delete(999) is False

    asyncio.run(run_test())


def test_get_by_knowledge_base_with_chunk_counts_delegates_to_repository(database):
    """测试 Service 委托 Repository 查询文档及分块数量。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            document = await create_document(session, knowledge_base.id)
            service = DocumentService(session)

            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content="Service 聚合查询测试分块。",
                token_count=10,
                start_index=0,
                end_index=10,
            )
            session.add(chunk)
            await session.flush()

            items, total = await service.get_by_knowledge_base_with_chunk_counts(
                knowledge_base.id,
                offset=0,
                limit=10,
            )

            assert total == 1
            assert len(items) == 1
            assert items[0][0].id == document.id
            assert items[0][1] == 1

    asyncio.run(run_test())
