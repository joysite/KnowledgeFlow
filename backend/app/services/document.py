"""KnowledgeFlow 文档业务服务。"""

import re
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document
from app.repositories import DocumentRepository, KnowledgeBaseRepository


class DocumentService:
    """处理文档业务逻辑和事务管理。"""

    ALLOWED_STATUSES = frozenset({"pending", "processing", "completed", "failed"})
    ALLOWED_UPDATE_FIELDS = frozenset({"name", "file_type", "file_path", "file_size"})
    SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

    def __init__(self, session: AsyncSession) -> None:
        """初始化文档 Service。"""
        self.session = session
        self.repository = DocumentRepository(session)
        self.knowledge_base_repository = KnowledgeBaseRepository(session)

    @staticmethod
    def _validate_name(name: str) -> str:
        """校验并规范化文档名称。"""
        if not isinstance(name, str):
            raise TypeError("name 必须是字符串")

        normalized = name.strip()

        if not normalized:
            raise ValueError("文档名称不能为空")

        if len(normalized) > 255:
            raise ValueError("文档名称长度不能超过 255 个字符")

        return normalized

    @staticmethod
    def _validate_file_type(file_type: str) -> str:
        """校验并规范化文件类型。"""
        if not isinstance(file_type, str):
            raise TypeError("file_type 必须是字符串")

        normalized = file_type.strip().lower()

        if not normalized:
            raise ValueError("文件类型不能为空")

        if len(normalized) > 20:
            raise ValueError("文件类型长度不能超过 20 个字符")

        return normalized

    @staticmethod
    def _validate_file_path(file_path: str) -> str:
        """校验并规范化文件路径。"""
        if not isinstance(file_path, str):
            raise TypeError("file_path 必须是字符串")

        normalized = file_path.strip()

        if not normalized:
            raise ValueError("文件路径不能为空")

        if len(normalized) > 1024:
            raise ValueError("文件路径长度不能超过 1024 个字符")

        return normalized

    @staticmethod
    def _validate_file_size(file_size: int) -> int:
        """校验文件大小。"""
        if isinstance(file_size, bool) or not isinstance(file_size, int):
            raise TypeError("file_size 必须是整数")

        if file_size < 0:
            raise ValueError("file_size 不能小于 0")

        return file_size

    @classmethod
    def _validate_content_hash(cls, content_hash: str) -> str:
        """校验并规范化 SHA-256 哈希值。"""
        if not isinstance(content_hash, str):
            raise TypeError("content_hash 必须是字符串")

        normalized = content_hash.strip()

        if not cls.SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("content_hash 必须是 64 位十六进制 SHA-256")

        return normalized.lower()

    @classmethod
    def _validate_status(cls, status: str) -> str:
        """校验文档处理状态。"""
        if not isinstance(status, str):
            raise TypeError("status 必须是字符串")

        if status not in cls.ALLOWED_STATUSES:
            raise ValueError(f"不支持的文档状态：{status}")

        return status

    @staticmethod
    def _validate_error_message(
        error_message: str | None,
    ) -> str | None:
        """校验文档处理错误信息。"""
        if error_message is not None and not isinstance(error_message, str):
            raise TypeError("error_message 必须是字符串或 None")

        if error_message is not None:
            error_message = error_message.strip()
            if not error_message:
                raise ValueError("error_message 不能为空字符串")

        return error_message

    @classmethod
    def _validate_create_data(
        cls,
        name: str,
        file_type: str,
        file_path: str,
        file_size: int,
        content_hash: str,
    ) -> dict[str, Any]:
        """校验创建文档所需的数据。"""
        return {
            "name": cls._validate_name(name),
            "file_type": cls._validate_file_type(file_type),
            "file_path": cls._validate_file_path(file_path),
            "file_size": cls._validate_file_size(file_size),
            "content_hash": cls._validate_content_hash(content_hash),
        }

    @classmethod
    def _validate_update_data(
        cls,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """校验文档更新字段并返回规范化数据。"""
        if not isinstance(data, dict):
            raise TypeError("data 必须是字典")

        if not data:
            raise ValueError("更新数据不能为空")

        for field in data:
            if field not in cls.ALLOWED_UPDATE_FIELDS:
                raise ValueError(f"不允许更新字段：{field}")

        validators = {
            "name": cls._validate_name,
            "file_type": cls._validate_file_type,
            "file_path": cls._validate_file_path,
            "file_size": cls._validate_file_size,
        }

        return {field: validators[field](value) for field, value in data.items()}

    async def create(
        self,
        knowledge_base_id: int,
        name: str,
        file_type: str,
        file_path: str,
        file_size: int,
        content_hash: str,
    ) -> Document:
        """
        创建文档。

        检查知识库是否存在，并在同一知识库内执行内容哈希去重。
        成功后提交事务；失败时回滚事务。
        """
        validated_data = self._validate_create_data(
            name,
            file_type,
            file_path,
            file_size,
            content_hash,
        )

        knowledge_base = await self.knowledge_base_repository.get_by_id(knowledge_base_id)

        if knowledge_base is None:
            raise ValueError(f"知识库不存在：{knowledge_base_id}")

        duplicated = await self.repository.get_by_content_hash(
            knowledge_base_id,
            validated_data["content_hash"],
        )

        if duplicated is not None:
            raise ValueError(f"该知识库中已存在相同内容的文档：{duplicated.id}")

        document = Document(
            knowledge_base_id=knowledge_base_id,
            **validated_data,
        )

        try:
            await self.repository.create(document)
            await self.session.commit()
            await self.session.refresh(document)
            return document
        except BaseException:
            await self.session.rollback()
            raise

    async def get_by_id(self, document_id: int) -> Document | None:
        """根据主键查询文档。"""
        return await self.repository.get_by_id(document_id)

    async def get_by_id_with_chunks(
        self,
        document_id: int,
    ) -> Document | None:
        """查询文档并预加载关联分块。"""
        return await self.repository.get_by_id_with_chunks(document_id)

    async def get_by_content_hash(
        self,
        knowledge_base_id: int,
        content_hash: str,
    ) -> Document | None:
        """在指定知识库内根据内容哈希查询文档。"""
        normalized_hash = self._validate_content_hash(content_hash)
        return await self.repository.get_by_content_hash(
            knowledge_base_id,
            normalized_hash,
        )

    async def get_by_knowledge_base(
        self,
        knowledge_base_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        """查询指定知识库下的文档。"""
        return await self.repository.get_by_knowledge_base(
            knowledge_base_id,
            offset=offset,
            limit=limit,
        )

    async def get_by_knowledge_base_with_chunk_counts(
        self,
        knowledge_base_id: int,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[tuple[Document, int]], int]:
        """分页查询知识库文档及分块数量。"""
        return await self.repository.get_by_knowledge_base_with_chunk_counts(
            knowledge_base_id,
            offset=offset,
            limit=limit,
        )

    async def get_stale_processing(
        self,
        updated_before: datetime,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        """
        查询更新时间早于指定阈值的处理中断文档。

        updated_before 使用 UTC 无时区时间，与数据库时间字段保持一致。
        """
        if not isinstance(updated_before, datetime):
            raise TypeError("updated_before 必须是 datetime 类型")

        if updated_before.tzinfo is not None and updated_before.utcoffset() is not None:
            raise ValueError("updated_before 必须是无时区 UTC 时间")

        self._validate_pagination(offset, limit)

        statement = (
            select(Document)
            .where(
                Document.status == "processing",
                Document.updated_at < updated_before,
            )
            .order_by(
                Document.updated_at.asc(),
                Document.id.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)

        return list(result.all())

    async def claim_stale_processing(
        self,
        document_id: int,
        updated_before: datetime,
    ) -> bool:
        """
        原子认领超时的处理中断文档。

        仅更新仍处于 processing 且更新时间早于阈值的文档。
        成功认领后刷新 updated_at，避免其他任务重复认领。

        本方法不提交事务，由调用方负责 commit 或 rollback。
        """
        if isinstance(document_id, bool) or not isinstance(document_id, int):
            raise TypeError("document_id 必须是整数")

        if document_id <= 0:
            raise ValueError("document_id 必须大于 0")

        if not isinstance(updated_before, datetime):
            raise TypeError("updated_before 必须是 datetime 类型")

        if updated_before.tzinfo is not None and updated_before.utcoffset() is not None:
            raise ValueError("updated_before 必须是无时区 UTC 时间")

        statement = (
            update(Document)
            .where(
                Document.id == document_id,
                Document.status == "processing",
                Document.updated_at < updated_before,
            )
            .values(updated_at=func.current_timestamp())
            .returning(Document.id)
            .execution_options(synchronize_session=False)
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none() is not None

    async def get_by_status(
        self,
        status: str,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Document]:
        """根据处理状态分页查询文档。"""
        return await self.repository.get_by_status(
            status,
            offset=offset,
            limit=limit,
        )

    async def update(
        self,
        document_id: int,
        data: dict[str, Any],
    ) -> Document | None:
        """
        更新文档元数据。

        不允许修改所属知识库、内容哈希和处理状态。
        文档不存在时返回 None。
        """
        validated_data = self._validate_update_data(data)

        document = await self.repository.get_by_id(document_id)

        if document is None:
            return None

        try:
            await self.repository.update(document, validated_data)
            await self.session.commit()
            await self.session.refresh(document)
            return document
        except BaseException:
            await self.session.rollback()
            raise

    async def update_status(
        self,
        document_id: int,
        status: str,
        error_message: str | None = None,
    ) -> Document | None:
        """
        更新文档处理状态。

        failed 状态必须提供错误原因；
        其他状态会自动清除之前的错误信息。
        """
        validated_status = self._validate_status(status)
        validated_error = self._validate_error_message(error_message)

        if validated_status == "failed" and validated_error is None:
            raise ValueError("failed 状态必须提供 error_message")

        document = await self.repository.get_by_id(document_id)

        if document is None:
            return None

        update_data = {
            "status": validated_status,
            "error_message": (validated_error if validated_status == "failed" else None),
        }

        try:
            await self.repository.update(document, update_data)
            await self.session.commit()
            await self.session.refresh(document)
            return document
        except BaseException:
            await self.session.rollback()
            raise

    async def delete(self, document_id: int) -> bool:
        """
        删除文档元数据。

        数据库通过外键级联删除关联分块。
        不负责删除磁盘上的原始文件。
        """
        document = await self.repository.get_by_id(document_id)

        if document is None:
            return False

        try:
            await self.repository.delete(document)
            await self.session.commit()
            return True
        except BaseException:
            await self.session.rollback()
            raise
