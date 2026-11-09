"""KnowledgeFlow 知识库彻底删除服务。"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.storage import LocalFileStorage
from app.repositories import DocumentRepository, KnowledgeBaseRepository
from app.services.knowledge_base_locks import KnowledgeBaseOperationLocks
from app.vectorstore.chroma import ChromaVectorStore


class KnowledgeBaseDeletionError(RuntimeError):
    """知识库外部资源清理失败。"""


class KnowledgeBaseDeletionService:
    """负责清理知识库关联的向量、文件和数据库记录。"""

    DOCUMENT_PAGE_SIZE = 100

    def __init__(
        self,
        session: AsyncSession,
        vector_store: ChromaVectorStore,
        operation_locks: KnowledgeBaseOperationLocks,
        file_storage: LocalFileStorage,
    ) -> None:
        """初始化知识库删除服务。"""
        self.session = session
        self.vector_store = vector_store
        self.operation_locks = operation_locks
        self.file_storage = file_storage
        self.knowledge_base_repository = KnowledgeBaseRepository(session)
        self.document_repository = DocumentRepository(session)

    async def _get_document_file_paths(
        self,
        knowledge_base_id: int,
    ) -> list[str]:
        """分页收集知识库关联的全部原始文件路径。"""
        file_paths: list[str] = []
        offset = 0

        while True:
            documents = await self.document_repository.get_by_knowledge_base(
                knowledge_base_id,
                offset=offset,
                limit=self.DOCUMENT_PAGE_SIZE,
            )

            file_paths.extend(document.file_path for document in documents)

            if len(documents) < self.DOCUMENT_PAGE_SIZE:
                break

            offset += self.DOCUMENT_PAGE_SIZE

        # 保持原始顺序，同时避免重复删除同一路径。
        return list(dict.fromkeys(file_paths))

    async def _save_deletion_error(self, knowledge_base_id: int, error: Exception) -> None:
        """记录清理失败原因，保留 deleting 状态以便重试。"""
        await self.session.rollback()

        knowledge_base = await self.knowledge_base_repository.get_by_id(knowledge_base_id)

        if knowledge_base is None:
            return

        message = str(error).strip() or type(error).__name__
        knowledge_base.deletion_error = message

        await self.session.commit()

    async def delete(self, knowledge_base_id: int) -> bool:
        """
        彻底删除知识库。

        清理失败时保留知识库记录和 deleting 状态，允许再次调用重试。

        Returns:
            成功删除返回 True；知识库不存在返回 False。

        Raises:
            KnowledgeBaseDeletionError: 外部资源或数据库清理失败。
        """
        async with self.operation_locks.hold(knowledge_base_id):
            knowledge_base = await self.knowledge_base_repository.get_by_id(knowledge_base_id)

            if knowledge_base is None:
                return False

            if knowledge_base.status == "active":
                knowledge_base.status = "deleting"
                knowledge_base.deletion_error = None
                await self.session.commit()
            elif knowledge_base.status != "deleting":
                raise RuntimeError(f"知识库处于不支持的删除状态：{knowledge_base.status}")

            try:
                file_paths = await self._get_document_file_paths(knowledge_base_id)

                # 外部资源先清理，数据库记录最后删除。
                self.vector_store.delete_collection(f"knowledge_base_{knowledge_base_id}")

                for file_path in file_paths:
                    await self.file_storage.delete(file_path)

                # 外键级联删除文档及其全部分块。
                knowledge_base = await self.knowledge_base_repository.get_by_id(knowledge_base_id)

                if knowledge_base is not None:
                    await self.knowledge_base_repository.delete(knowledge_base)
                    await self.session.commit()

                return True

            except Exception as exc:
                try:
                    await self._save_deletion_error(
                        knowledge_base_id,
                        exc,
                    )
                except Exception as persistence_error:
                    await self.session.rollback()
                    raise KnowledgeBaseDeletionError(
                        f"知识库清理失败，且无法保存失败原因：{persistence_error}"
                    ) from exc

                raise KnowledgeBaseDeletionError(f"知识库删除清理失败：{exc}") from exc
