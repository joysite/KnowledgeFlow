"""KnowledgeFlow KnowledgeBaseRepository 测试。"""

import asyncio

import pytest
from sqlalchemy import inspect

from app.models import Document, KnowledgeBase
from app.repositories import KnowledgeBaseRepository


def test_repository_initializes_with_knowledge_base_model(database):
    """测试 Repository 正确绑定 KnowledgeBase 模型。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = KnowledgeBaseRepository(session)

            assert repository.session is session
            assert repository.model is KnowledgeBase

    asyncio.run(run_test())


def test_get_by_id_with_documents_returns_knowledge_base(database):
    """测试查询知识库时能够预加载关联文档。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = KnowledgeBaseRepository(session)

            knowledge_base = KnowledgeBase(name="文档预加载测试")
            session.add(knowledge_base)
            await session.flush()

            document = Document(
                knowledge_base_id=knowledge_base.id,
                name="测试文档",
                file_type="txt",
                file_path="/tmp/test.txt",
                file_size=10,
                content_hash="a" * 64,
            )
            session.add(document)
            await session.flush()

            result = await repository.get_by_id_with_documents(knowledge_base.id)

            assert result is not None
            assert result.id == knowledge_base.id
            assert len(result.documents) == 1
            assert result.documents[0].name == "测试文档"
            assert "documents" not in inspect(result).unloaded

    asyncio.run(run_test())


def test_get_by_id_with_documents_returns_none_when_not_found(database):
    """测试查询不存在的知识库时返回 None。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = KnowledgeBaseRepository(session)

            result = await repository.get_by_id_with_documents(999)

            assert result is None

    asyncio.run(run_test())


def test_list_all_with_document_counts(database):
    """测试分页查询知识库时统计文档数量，包含零文档知识库。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            first = KnowledgeBase(name="无文档知识库")
            second = KnowledgeBase(name="两个文档知识库")
            third = KnowledgeBase(name="一个文档知识库")
            session.add_all([first, second, third])
            await session.flush()

            session.add_all(
                [
                    Document(
                        knowledge_base_id=second.id,
                        name="文档一.txt",
                        file_type="txt",
                        file_path="/tmp/one.txt",
                        file_size=10,
                        content_hash="a" * 64,
                    ),
                    Document(
                        knowledge_base_id=second.id,
                        name="文档二.txt",
                        file_type="txt",
                        file_path="/tmp/two.txt",
                        file_size=20,
                        content_hash="b" * 64,
                    ),
                    Document(
                        knowledge_base_id=third.id,
                        name="文档三.txt",
                        file_type="txt",
                        file_path="/tmp/three.txt",
                        file_size=30,
                        content_hash="c" * 64,
                    ),
                ]
            )
            await session.flush()

            repository = KnowledgeBaseRepository(session)
            results = await repository.list_all_with_document_counts()

            assert [(item.id, count) for item, count in results] == [
                (first.id, 0),
                (second.id, 2),
                (third.id, 1),
            ]

            page = await repository.list_all_with_document_counts(
                offset=1,
                limit=1,
            )
            assert [(item.id, count) for item, count in page] == [(second.id, 2)]

    asyncio.run(run_test())


def test_list_all_with_document_counts_supports_keyword(database):
    """测试聚合列表按名称关键词过滤并保留文档数量。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            matched = KnowledgeBase(name="Python 知识库")
            KnowledgeBase(name="Java 知识库")
            session.add_all([matched, KnowledgeBase(name="Python 笔记")])
            await session.flush()

            session.add(
                Document(
                    knowledge_base_id=matched.id,
                    name="Python.txt",
                    file_type="txt",
                    file_path="/tmp/python.txt",
                    file_size=10,
                    content_hash="e" * 64,
                )
            )
            await session.flush()

            repository = KnowledgeBaseRepository(session)
            results = await repository.list_all_with_document_counts(
                keyword=" Python ",
            )

            assert [(item.name, count) for item, count in results] == [
                ("Python 知识库", 1),
                ("Python 笔记", 0),
            ]

            empty = await repository.list_all_with_document_counts(keyword="不存在")
            assert empty == []

    asyncio.run(run_test())


def test_search_by_name_returns_matching_entities(database):
    """测试根据名称关键词进行包含搜索。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = KnowledgeBaseRepository(session)

            session.add_all(
                [
                    KnowledgeBase(name="Python 开发知识库"),
                    KnowledgeBase(name="机器学习知识库"),
                    KnowledgeBase(name="Python 学习笔记"),
                ]
            )
            await session.flush()

            result = await repository.search_by_name("Python")

            assert len(result) == 2
            assert {item.name for item in result} == {
                "Python 开发知识库",
                "Python 学习笔记",
            }

    asyncio.run(run_test())


def test_search_by_name_supports_duplicate_names(database):
    """测试搜索允许返回名称相同的多个知识库。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = KnowledgeBaseRepository(session)

            session.add_all(
                [
                    KnowledgeBase(name="相同名称"),
                    KnowledgeBase(name="相同名称"),
                ]
            )
            await session.flush()

            result = await repository.search_by_name("相同名称")

            assert len(result) == 2
            assert result[0].id < result[1].id

    asyncio.run(run_test())


def test_search_by_name_supports_pagination(database):
    """测试名称搜索支持分页且顺序稳定。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = KnowledgeBaseRepository(session)

            session.add_all(
                [
                    KnowledgeBase(name="测试知识库一"),
                    KnowledgeBase(name="测试知识库二"),
                    KnowledgeBase(name="测试知识库三"),
                ]
            )
            await session.flush()

            first_page = await repository.search_by_name(
                "测试知识库",
                offset=0,
                limit=2,
            )
            second_page = await repository.search_by_name(
                "测试知识库",
                offset=2,
                limit=2,
            )

            assert len(first_page) == 2
            assert len(second_page) == 1
            assert first_page[0].id < first_page[1].id
            assert first_page[1].id < second_page[0].id

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "keyword",
    [
        "",
        "   ",
    ],
    ids=[
        "empty-keyword",
        "whitespace-keyword",
    ],
)
def test_search_by_name_rejects_empty_keyword(database, keyword):
    """测试名称搜索拒绝空关键词。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = KnowledgeBaseRepository(session)

            with pytest.raises(ValueError, match="keyword 不能为空"):
                await repository.search_by_name(keyword)

    asyncio.run(run_test())


def test_search_by_name_rejects_non_string_keyword(database):
    """测试名称搜索拒绝非字符串关键词。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = KnowledgeBaseRepository(session)

            with pytest.raises(TypeError, match="keyword 必须是字符串"):
                await repository.search_by_name(None)

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("offset", "limit", "message"),
    [
        (-1, 10, "offset 不能小于 0"),
        (0, 0, "limit 必须大于 0"),
        (0, -1, "limit 必须大于 0"),
    ],
)
def test_search_by_name_rejects_invalid_pagination(
    database,
    offset,
    limit,
    message,
):
    """测试名称搜索拒绝非法分页参数。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            repository = KnowledgeBaseRepository(session)

            with pytest.raises(ValueError, match=message):
                await repository.search_by_name(
                    "测试",
                    offset=offset,
                    limit=limit,
                )

    asyncio.run(run_test())
