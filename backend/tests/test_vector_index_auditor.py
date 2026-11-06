"""向量索引一致性审计测试。"""

import asyncio
from types import SimpleNamespace

from app.models import Document, DocumentChunk, KnowledgeBase
from app.reindex.auditor import VectorIndexAuditor


class FakeVectorStore:
    """模拟只读 Chroma 查询。"""

    def __init__(
        self,
        records=None,
        collection_exists=True,
        collection_name="knowledge_base_1",
    ):
        self.records = records or []
        self.collection_name = collection_name
        self.requested_collection_names = []
        self.client = SimpleNamespace(
            list_collections=lambda: (
                [SimpleNamespace(name=collection_name)] if collection_exists else []
            )
        )

    def get_all_records(self, collection_name, batch_size=500):
        self.requested_collection_names.append(collection_name)
        return self.records


async def seed_database(session):
    """创建一个包含两个分块的已完成文档。"""
    knowledge_base = KnowledgeBase(name="审计测试知识库")
    session.add(knowledge_base)
    await session.flush()

    document = Document(
        knowledge_base_id=knowledge_base.id,
        name="审计测试.txt",
        file_type="txt",
        file_path="uploads/audit.txt",
        file_size=100,
        content_hash="a" * 64,
        status="completed",
    )
    session.add(document)
    await session.flush()

    chunks = [
        DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            content=f"测试内容 {index}",
            token_count=10,
            start_index=index * 10,
            end_index=index * 10 + 10,
        )
        for index in range(2)
    ]
    session.add_all(chunks)
    await session.flush()

    return knowledge_base, document, chunks


def make_records(knowledge_base_id, document_id, chunks):
    """根据数据库分块构造对应的 Chroma 记录。"""
    return [
        {
            "id": str(chunk.id),
            "metadata": {
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
            },
        }
        for chunk in chunks
    ]


def test_audit_reports_consistent_index(database):
    """验证 SQLite 和 Chroma 完全一致。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb, document, chunks = await seed_database(session)
            store = FakeVectorStore(make_records(kb.id, document.id, chunks))

            report = await VectorIndexAuditor(session, store).audit(kb.id)

            assert report.knowledge_base_exists is True
            assert report.collection_exists is True
            assert report.sqlite_chunk_count == 2
            assert report.chroma_vector_count == 2
            assert report.missing_vector_ids == []
            assert report.orphan_vector_ids == []
            assert report.invalid_metadata_ids == []
            assert report.is_consistent is True

    asyncio.run(run_test())


def test_audit_detects_missing_vector(database):
    """验证检测 SQLite 中存在但 Chroma 缺失的向量。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb, document, chunks = await seed_database(session)
            records = make_records(kb.id, document.id, chunks[:1])

            report = await VectorIndexAuditor(session, FakeVectorStore(records)).audit(kb.id)

            assert report.missing_vector_ids == [str(chunks[1].id)]
            assert report.orphan_vector_ids == []
            assert report.is_consistent is False

    asyncio.run(run_test())


def test_audit_detects_orphan_vector(database):
    """验证检测 Chroma 中 SQLite 不存在的向量。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb, document, chunks = await seed_database(session)
            records = make_records(kb.id, document.id, chunks)
            records.append(
                {
                    "id": "99999",
                    "metadata": {
                        "knowledge_base_id": kb.id,
                        "document_id": document.id,
                        "chunk_index": 99,
                    },
                }
            )

            report = await VectorIndexAuditor(session, FakeVectorStore(records)).audit(kb.id)

            assert report.orphan_vector_ids == ["99999"]
            assert report.is_consistent is False

    asyncio.run(run_test())


def test_audit_detects_invalid_metadata(database):
    """验证检测错误的知识库、文档或分块元数据。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb, document, chunks = await seed_database(session)
            records = make_records(kb.id, document.id, chunks)
            records[0]["metadata"]["knowledge_base_id"] = 999

            report = await VectorIndexAuditor(session, FakeVectorStore(records)).audit(kb.id)

            assert report.invalid_metadata_ids == [str(chunks[0].id)]
            assert report.is_consistent is False

    asyncio.run(run_test())


def test_audit_reports_missing_knowledge_base(database):
    """验证不存在的知识库不会被判定为一致。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            report = await VectorIndexAuditor(session, FakeVectorStore()).audit(999)

            assert report.knowledge_base_exists is False
            assert report.is_consistent is False

    asyncio.run(run_test())


def test_audit_reports_missing_collection(database):
    """验证不存在的 Collection 不会被自动创建。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb, _, _ = await seed_database(session)
            store = FakeVectorStore(collection_exists=False)

            report = await VectorIndexAuditor(session, store).audit(kb.id)

            assert report.collection_exists is False
            assert report.chroma_vector_count == 0
            assert len(report.missing_vector_ids) == 2
            assert report.is_consistent is False

    asyncio.run(run_test())


def test_audit_supports_custom_collection_name(database):
    """验证审计器可以检查指定的临时集合。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            kb, document, chunks = await seed_database(session)
            custom_name = "knowledge_base_1_rebuild"

            store = FakeVectorStore(
                records=make_records(kb.id, document.id, chunks),
                collection_name=custom_name,
            )

            report = await VectorIndexAuditor(session, store).audit(
                kb.id,
                collection_name=custom_name,
            )

            assert report.collection_exists is True
            assert report.is_consistent is True
            assert store.requested_collection_names == [custom_name]

    asyncio.run(run_test())
