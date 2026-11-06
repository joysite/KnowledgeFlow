"""BM25 关键词检索服务测试。"""

import pytest

from app.ingestion.tokenizers import BertWordPieceTokenizer
from app.models import Document, DocumentChunk, KnowledgeBase
from app.services.bm25_search import BM25SearchService


async def create_completed_document(session, knowledge_base, name, content_hash):
    """创建已完成文档。"""
    document = Document(
        knowledge_base_id=knowledge_base.id,
        name=name,
        file_type="txt",
        file_path=f"uploads/{name}",
        file_size=1024,
        content_hash=content_hash * 64,
        status="completed",
    )
    session.add(document)
    await session.flush()
    return document


async def create_chunk(session, document, index, content):
    """创建文档分块。"""
    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=index,
        content=content,
        token_count=10,
        start_index=index * 100,
        end_index=index * 100 + len(content),
    )
    session.add(chunk)
    await session.flush()
    return chunk


@pytest.mark.asyncio
async def test_search_returns_matching_chunks_from_sqlite(database):
    """验证 BM25 能从 SQLite 检索并映射分块信息。"""
    _, session_factory = database

    async with session_factory() as session:
        knowledge_base = KnowledgeBase(name="BM25 测试知识库")
        session.add(knowledge_base)
        await session.flush()

        document = await create_completed_document(session, knowledge_base, "Python 指南.txt", "a")
        expected = await create_chunk(
            session, document, 0, "Python FastAPI 是一个高性能 Web 框架。"
        )
        await create_chunk(session, document, 1, "Java Spring 是另一个 Web 框架。")

        service = BM25SearchService(session)
        results = await service.search("Python FastAPI", knowledge_base.id)

        assert len(results) == 1
        assert results[0].chunk_id == expected.id
        assert results[0].document_id == document.id
        assert results[0].document_name == "Python 指南.txt"
        assert results[0].chunk_index == 0
        assert results[0].content == expected.content
        assert results[0].token_count == expected.token_count
        assert results[0].score > 0


@pytest.mark.asyncio
async def test_search_scopes_knowledge_base_and_completed_documents(database):
    """验证只召回指定知识库中的已完成文档。"""
    _, session_factory = database

    async with session_factory() as session:
        first_kb = KnowledgeBase(name="知识库一")
        second_kb = KnowledgeBase(name="知识库二")
        session.add_all([first_kb, second_kb])
        await session.flush()

        first_doc = await create_completed_document(session, first_kb, "文档一.txt", "b")
        await create_chunk(session, first_doc, 0, "Python FastAPI 检索服务")

        second_doc = await create_completed_document(session, second_kb, "文档二.txt", "c")
        await create_chunk(session, second_doc, 0, "Python FastAPI 其他知识")

        pending_doc = Document(
            knowledge_base_id=first_kb.id,
            name="待处理.txt",
            file_type="txt",
            file_path="uploads/待处理.txt",
            file_size=1024,
            content_hash="d" * 64,
            status="pending",
        )
        session.add(pending_doc)
        await session.flush()
        await create_chunk(session, pending_doc, 0, "Python FastAPI 待处理内容")

        service = BM25SearchService(session)
        results = await service.search("Python FastAPI", first_kb.id)

        assert len(results) == 1
        assert results[0].document_id == first_doc.id


@pytest.mark.asyncio
async def test_search_respects_top_k(database):
    """验证 BM25 服务正确限制返回数量。"""
    _, session_factory = database

    async with session_factory() as session:
        knowledge_base = KnowledgeBase(name="TopK 测试")
        session.add(knowledge_base)
        await session.flush()

        document = await create_completed_document(session, knowledge_base, "多分块.txt", "e")

        for index in range(4):
            await create_chunk(
                session,
                document,
                index,
                f"Python FastAPI 检索内容 {index}",
            )

        service = BM25SearchService(session)
        results = await service.search("Python FastAPI", knowledge_base.id, top_k=2)

        assert len(results) == 2
        assert all(item.score > 0 for item in results)


@pytest.mark.asyncio
async def test_search_returns_empty_for_empty_knowledge_base(database):
    """验证空知识库返回空结果。"""
    _, session_factory = database

    async with session_factory() as session:
        knowledge_base = KnowledgeBase(name="空知识库")
        session.add(knowledge_base)
        await session.flush()

        service = BM25SearchService(session)
        results = await service.search("Python", knowledge_base.id)

        assert results == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "knowledge_base_id", "top_k", "error"),
    [
        ("", 1, 5, ValueError),
        ("   ", 1, 5, ValueError),
        ("Python", 0, 5, ValueError),
        ("Python", True, 5, TypeError),
        ("Python", 1, 0, ValueError),
        ("Python", 1, True, TypeError),
    ],
)
async def test_search_rejects_invalid_inputs(database, query, knowledge_base_id, top_k, error):
    """验证非法参数在查询数据库前被拒绝。"""
    _, session_factory = database

    async with session_factory() as session:
        service = BM25SearchService(session)

        with pytest.raises(error):
            await service.search(query, knowledge_base_id, top_k)


@pytest.mark.asyncio
async def test_search_uses_shared_wordpiece_tokenizer(database):
    """验证查询和文档使用同一 WordPiece 分词规则。"""
    _, session_factory = database

    async with session_factory() as session:
        knowledge_base = KnowledgeBase(name="Tokenizer 测试")
        session.add(knowledge_base)
        await session.flush()

        document = await create_completed_document(session, knowledge_base, "中文.txt", "f")
        expected = await create_chunk(session, document, 0, "hello 世界")

        tokenizer = BertWordPieceTokenizer()
        service = BM25SearchService(session, tokenizer=tokenizer)

        results = await service.search("hello", knowledge_base.id)

        assert results
        assert results[0].chunk_id == expected.id
        assert results[0].score > 0


@pytest.mark.asyncio
async def test_search_matches_markdown_heading_and_preserves_original_content(database):
    """验证 BM25 能检索标题上下文，同时返回原始正文。"""
    _, session_factory = database

    async with session_factory() as session:
        knowledge_base = KnowledgeBase(name="Markdown 标题检索测试")
        session.add(knowledge_base)
        await session.flush()

        document = await create_completed_document(session, knowledge_base, "部署指南.md", "a")
        chunk = await create_chunk(session, document, 0, "执行以下命令完成部署。")
        chunk.chunk_metadata = {"heading_path": ["Python", "部署指南"]}

        await session.flush()

        service = BM25SearchService(session)
        results = await service.search("Python", knowledge_base.id)

        assert len(results) == 1
        assert results[0].chunk_id == chunk.id
        assert results[0].content == "执行以下命令完成部署。"
