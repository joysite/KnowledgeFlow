"""KnowledgeFlow 知识库彻底删除服务测试。"""

import asyncio
from pathlib import Path

import pytest
from chromadb.errors import NotFoundError
from sqlalchemy import func, select

from app.ingestion.storage import LocalFileStorage
from app.models import Document, DocumentChunk, KnowledgeBase
from app.services import (
    KnowledgeBaseDeletionError,
    KnowledgeBaseDeletionService,
)
from app.services.knowledge_base_locks import KnowledgeBaseOperationLocks
from app.vectorstore.chroma import ChromaVectorStore


async def create_test_knowledge_base(
    session,
    upload_dir: Path,
    document_count: int = 1,
) -> tuple[KnowledgeBase, list[Path]]:
    """创建包含文档、分块和真实临时文件的测试知识库。"""
    knowledge_base = KnowledgeBase(name="待删除知识库")
    session.add(knowledge_base)
    await session.flush()

    file_paths = []

    for index in range(document_count):
        file_path = upload_dir / f"document-{index}.txt"
        file_path.write_text(f"测试文档内容 {index}", encoding="utf-8")
        file_paths.append(file_path)

        document = Document(
            knowledge_base_id=knowledge_base.id,
            name=f"document-{index}.txt",
            file_type="txt",
            file_path=str(file_path),
            file_size=file_path.stat().st_size,
            content_hash=f"{index:064x}",
            status="completed" if index % 2 == 0 else "failed",
        )
        session.add(document)
        await session.flush()

        session.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                content=f"测试分块内容 {index}",
                token_count=10,
                start_index=0,
                end_index=10,
            )
        )

    await session.commit()
    return knowledge_base, file_paths


def create_service(session, tmp_path: Path):
    """创建完全隔离的删除服务。"""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    vector_store = ChromaVectorStore(tmp_path / "chroma")
    file_storage = LocalFileStorage(upload_dir)

    service = KnowledgeBaseDeletionService(
        session=session,
        vector_store=vector_store,
        operation_locks=KnowledgeBaseOperationLocks(),
        file_storage=file_storage,
    )

    return service, vector_store, file_storage, upload_dir


def test_delete_knowledge_base_removes_all_resources(database, tmp_path):
    """成功删除时清理向量集合、上传文件、文档和分块。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service, vector_store, _, upload_dir = create_service(
                session,
                tmp_path,
            )
            knowledge_base, file_paths = await create_test_knowledge_base(
                session,
                upload_dir,
                document_count=2,
            )
            knowledge_base_id = knowledge_base.id

            collection_name = f"knowledge_base_{knowledge_base_id}"
            vector_store.get_or_create_collection(collection_name).upsert(
                ids=["vector-1"],
                embeddings=[[0.1, 0.2, 0.3]],
            )

            result = await service.delete(knowledge_base_id)

            assert result is True
            assert all(not path.exists() for path in file_paths)
            assert upload_dir.is_dir()

            with pytest.raises(NotFoundError):
                vector_store.client.get_collection(name=collection_name)

            assert await session.scalar(select(func.count()).select_from(KnowledgeBase)) == 0
            assert await session.scalar(select(func.count()).select_from(Document)) == 0
            assert await session.scalar(select(func.count()).select_from(DocumentChunk)) == 0

    asyncio.run(run_test())


def test_delete_failure_preserves_state_and_can_retry(
    database,
    tmp_path,
    monkeypatch,
):
    """文件清理失败时保留 deleting 状态，修复后可以重试。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service, vector_store, file_storage, upload_dir = create_service(
                session,
                tmp_path,
            )
            knowledge_base, file_paths = await create_test_knowledge_base(
                session,
                upload_dir,
            )
            knowledge_base_id = knowledge_base.id

            collection_name = f"knowledge_base_{knowledge_base_id}"
            vector_store.get_or_create_collection(collection_name)

            async def fail_delete(file_path):
                raise OSError("模拟文件删除失败")

            monkeypatch.setattr(file_storage, "delete", fail_delete)

            with pytest.raises(
                KnowledgeBaseDeletionError,
                match="模拟文件删除失败",
            ):
                await service.delete(knowledge_base_id)

            await session.refresh(knowledge_base)
            assert knowledge_base.status == "deleting"
            assert "模拟文件删除失败" in knowledge_base.deletion_error
            assert file_paths[0].exists()

            # 向量集合已被清理；重试时删除不存在的集合应当成功。
            with pytest.raises(NotFoundError):
                vector_store.client.get_collection(name=collection_name)

            monkeypatch.undo()

            result = await service.delete(knowledge_base_id)

            assert result is True
            assert not file_paths[0].exists()
            assert await session.get(KnowledgeBase, knowledge_base_id) is None

    asyncio.run(run_test())


def test_delete_returns_false_when_knowledge_base_not_found(database, tmp_path):
    """删除不存在的知识库时返回 False，不创建任何外部资源。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service, vector_store, _, _ = create_service(session, tmp_path)

            result = await service.delete(999)

            assert result is False
            assert vector_store.client.list_collections() == []

    asyncio.run(run_test())


def test_delete_knowledge_base_handles_multiple_document_pages(database, tmp_path):
    """文档数量超过单页限制时仍能完整删除。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service, _, _, upload_dir = create_service(session, tmp_path)
            knowledge_base, file_paths = await create_test_knowledge_base(
                session,
                upload_dir,
                document_count=101,
            )

            knowledge_base_id = knowledge_base.id

            result = await service.delete(knowledge_base_id)

            assert result is True
            assert len(file_paths) == 101
            assert all(not path.exists() for path in file_paths)
            assert await session.get(KnowledgeBase, knowledge_base_id) is None
            assert await session.scalar(select(func.count()).select_from(Document)) == 0
            assert await session.scalar(select(func.count()).select_from(DocumentChunk)) == 0

    asyncio.run(run_test())
