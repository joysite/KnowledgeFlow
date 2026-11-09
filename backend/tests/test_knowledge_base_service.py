"""KnowledgeFlow KnowledgeBaseService 测试。"""

import asyncio

import pytest
from sqlalchemy import func, select

from app.models import Document, DocumentChunk, KnowledgeBase
from app.services import KnowledgeBaseService


async def create_knowledge_base(
    session,
    name: str = "测试知识库",
) -> KnowledgeBase:
    """创建测试知识库。"""
    knowledge_base = KnowledgeBase(name=name)
    session.add(knowledge_base)
    await session.flush()
    return knowledge_base


def test_service_initializes_with_session(database):
    """测试 Service 正确初始化。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            assert service.session is session
            assert service.repository.session is session

    asyncio.run(run_test())


def test_create_knowledge_base(database):
    """测试创建知识库并持久化。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            result = await service.create(
                "  Python 知识库  ",
                "用于保存 Python 学习资料",
            )

            assert result.id is not None
            assert result.name == "Python 知识库"
            assert result.description == "用于保存 Python 学习资料"
            assert result.created_at is not None
            assert result.updated_at is not None

        async with session_factory() as session:
            result = await session.get(KnowledgeBase, result.id)
            assert result is not None
            assert result.name == "Python 知识库"

    asyncio.run(run_test())


def test_create_knowledge_base_without_description(database):
    """测试创建没有描述的知识库。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            result = await service.create("无描述知识库")

            assert result.description is None

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
    ],
    ids=["empty-name", "whitespace-name"],
)
def test_create_rejects_empty_name(database, name):
    """测试创建知识库时拒绝空名称。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            with pytest.raises(ValueError, match="知识库名称不能为空"):
                await service.create(name)

    asyncio.run(run_test())


def test_create_rejects_non_string_name(database):
    """测试创建知识库时拒绝非字符串名称。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            with pytest.raises(TypeError, match="name 必须是字符串"):
                await service.create(None)

    asyncio.run(run_test())


def test_create_rejects_name_longer_than_128_characters(database):
    """测试创建知识库时拒绝超长名称。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            with pytest.raises(ValueError, match="不能超过 128"):
                await service.create("a" * 129)

    asyncio.run(run_test())


def test_create_rejects_invalid_description(database):
    """测试创建知识库时拒绝非法描述类型。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            with pytest.raises(
                TypeError,
                match="description 必须是字符串或 None",
            ):
                await service.create("测试知识库", 123)

    asyncio.run(run_test())


def test_get_by_id_returns_knowledge_base(database):
    """测试根据 ID 查询知识库。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            service = KnowledgeBaseService(session)

            result = await service.get_by_id(knowledge_base.id)

            assert result is not None
            assert result.id == knowledge_base.id

    asyncio.run(run_test())


def test_get_by_id_returns_none_when_not_found(database):
    """测试查询不存在的知识库。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            result = await service.get_by_id(99999)

            assert result is None

    asyncio.run(run_test())


def test_get_by_id_with_documents(database):
    """测试查询知识库并预加载关联文档。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)

            document = Document(
                knowledge_base_id=knowledge_base.id,
                name="测试文档.txt",
                file_type="txt",
                file_path="uploads/test.txt",
                file_size=100,
                content_hash="a" * 64,
            )
            session.add(document)
            await session.flush()

            service = KnowledgeBaseService(session)
            result = await service.get_by_id_with_documents(knowledge_base.id)

            assert result is not None
            assert len(result.documents) == 1
            assert result.documents[0].name == "测试文档.txt"

    asyncio.run(run_test())


def test_get_by_id_with_documents_returns_none_when_not_found(database):
    """测试预加载查询不存在的知识库。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            result = await service.get_by_id_with_documents(99999)

            assert result is None

    asyncio.run(run_test())


def test_list_all_with_document_counts(database):
    """测试 Service 返回知识库及对应文档数量。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            first = await create_knowledge_base(session, "无文档知识库")
            second = await create_knowledge_base(session, "有文档知识库")
            session.add(
                Document(
                    knowledge_base_id=second.id,
                    name="测试文档.txt",
                    file_type="txt",
                    file_path="/tmp/test.txt",
                    file_size=10,
                    content_hash="d" * 64,
                )
            )
            await session.flush()

            service = KnowledgeBaseService(session)
            results = await service.list_all_with_document_counts()

            assert [(item.id, count) for item, count in results] == [
                (first.id, 0),
                (second.id, 1),
            ]

    asyncio.run(run_test())


def test_search_by_name(database):
    """测试根据名称关键词搜索知识库。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            session.add_all(
                [
                    KnowledgeBase(name="Python 开发知识库"),
                    KnowledgeBase(name="机器学习知识库"),
                    KnowledgeBase(name="Python 学习笔记"),
                ]
            )
            await session.flush()

            service = KnowledgeBaseService(session)
            result = await service.search_by_name("Python")

            assert len(result) == 2
            assert {item.name for item in result} == {
                "Python 开发知识库",
                "Python 学习笔记",
            }

    asyncio.run(run_test())


def test_search_by_name_supports_pagination(database):
    """测试知识库搜索支持分页。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            session.add_all(
                [
                    KnowledgeBase(name="测试知识库一"),
                    KnowledgeBase(name="测试知识库二"),
                    KnowledgeBase(name="测试知识库三"),
                ]
            )
            await session.flush()

            service = KnowledgeBaseService(session)
            first_page = await service.search_by_name(
                "测试知识库",
                offset=0,
                limit=2,
            )
            second_page = await service.search_by_name(
                "测试知识库",
                offset=2,
                limit=2,
            )

            assert len(first_page) == 2
            assert len(second_page) == 1

    asyncio.run(run_test())


def test_update_knowledge_base_name(database):
    """测试更新知识库名称。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            service = KnowledgeBaseService(session)

            result = await service.update(
                knowledge_base.id,
                {"name": "更新后的名称"},
            )

            assert result is not None
            assert result.name == "更新后的名称"

        async with session_factory() as session:
            result = await session.get(KnowledgeBase, knowledge_base.id)
            assert result.name == "更新后的名称"

    asyncio.run(run_test())


def test_update_knowledge_base_description(database):
    """测试更新知识库描述。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            service = KnowledgeBaseService(session)

            result = await service.update(
                knowledge_base.id,
                {"description": "新的描述"},
            )

            assert result is not None
            assert result.description == "新的描述"

    asyncio.run(run_test())


def test_update_can_clear_description(database):
    """测试允许将知识库描述设置为 None。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            knowledge_base.description = "原描述"
            await session.flush()

            service = KnowledgeBaseService(session)
            result = await service.update(
                knowledge_base.id,
                {"description": None},
            )

            assert result is not None
            assert result.description is None

    asyncio.run(run_test())


def test_update_multiple_fields(database):
    """测试一次更新多个知识库字段。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            service = KnowledgeBaseService(session)

            result = await service.update(
                knowledge_base.id,
                {
                    "name": "新名称",
                    "description": "新描述",
                },
            )

            assert result is not None
            assert result.name == "新名称"
            assert result.description == "新描述"

    asyncio.run(run_test())


def test_update_returns_none_when_not_found(database):
    """测试更新不存在的知识库。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            result = await service.update(99999, {"name": "新名称"})

            assert result is None

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"id": 1},
        {"created_at": None},
        {"documents": []},
        {"unknown": "value"},
    ],
)
def test_update_rejects_invalid_fields(database, data):
    """测试更新操作拒绝空数据和非允许字段。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            with pytest.raises(ValueError):
                await service.update(1, data)

    asyncio.run(run_test())


def test_update_rejects_non_dict_data(database):
    """测试更新操作拒绝非字典数据。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            with pytest.raises(TypeError, match="data 必须是字典"):
                await service.update(1, None)

    asyncio.run(run_test())


def test_update_rejects_invalid_name_without_partial_changes(database):
    """测试更新数据校验失败时不产生部分修改。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            original_name = knowledge_base.name
            service = KnowledgeBaseService(session)

            with pytest.raises(ValueError, match="知识库名称不能为空"):
                await service.update(
                    knowledge_base.id,
                    {
                        "description": "不应被保存的描述",
                        "name": "   ",
                    },
                )

            assert knowledge_base.name == original_name
            assert knowledge_base.description is None

    asyncio.run(run_test())


def test_update_rejects_invalid_description(database):
    """测试更新操作拒绝非法描述类型。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            with pytest.raises(TypeError, match="description"):
                await service.update(1, {"description": 123})

    asyncio.run(run_test())


def test_delete_knowledge_base(database):
    """测试删除知识库并提交事务。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)
            knowledge_base_id = knowledge_base.id
            service = KnowledgeBaseService(session)

            result = await service.delete(knowledge_base_id)

            assert result is True

        async with session_factory() as session:
            result = await session.get(KnowledgeBase, knowledge_base_id)
            assert result is None

    asyncio.run(run_test())


def test_delete_cascades_document_and_chunk_metadata(database):
    """测试删除知识库时级联删除文档和分块元数据。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            knowledge_base = await create_knowledge_base(session)

            document = Document(
                knowledge_base_id=knowledge_base.id,
                name="级联测试.txt",
                file_type="txt",
                file_path="uploads/cascade.txt",
                file_size=100,
                content_hash="b" * 64,
            )
            session.add(document)
            await session.flush()

            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content="级联删除测试内容",
                token_count=5,
                start_index=0,
                end_index=9,
            )
            session.add(chunk)
            await session.flush()

            knowledge_base_id = knowledge_base.id
            document_id = document.id
            chunk_id = chunk.id

            service = KnowledgeBaseService(session)
            result = await service.delete(knowledge_base_id)

            assert result is True

            document_count = await session.scalar(
                select(func.count()).select_from(Document).where(Document.id == document_id)
            )
            chunk_count = await session.scalar(
                select(func.count()).select_from(DocumentChunk).where(DocumentChunk.id == chunk_id)
            )

            assert document_count == 0
            assert chunk_count == 0

    asyncio.run(run_test())


def test_delete_returns_false_when_not_found(database):
    """测试删除不存在的知识库。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = KnowledgeBaseService(session)

            result = await service.delete(99999)

            assert result is False

    asyncio.run(run_test())
