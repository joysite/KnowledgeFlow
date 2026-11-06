"""KnowledgeFlow 文档导入编排服务。"""

from dataclasses import replace
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.core.config import get_settings
from app.ingestion.chunk_processor import ChunkProcessor
from app.ingestion.chunker import TextChunk
from app.ingestion.cleaner import DocumentCleaner
from app.ingestion.parsers.base import ParsedDocument
from app.ingestion.parsers.registry import ParserRegistry
from app.ingestion.storage import LocalFileStorage, StoredFile
from app.ingestion.validators import UploadFileValidator, ValidatedFile
from app.models import Document, DocumentChunk
from app.repositories.document_chunk import DocumentChunkRepository
from app.services.document import DocumentService
from app.services.vector_index import VectorIndexService


class DocumentAlreadyExistsError(ValueError):
    """知识库中已存在相同内容的文档。"""

    def __init__(self, document_id: int) -> None:
        self.document_id = document_id
        super().__init__(f"该知识库中已存在相同内容的文档：{document_id}")


class EmptyDocumentContentError(ValueError):
    """文档清洗后没有有效文本内容。"""


class EmptyDocumentChunksError(ValueError):
    """文档分块后没有产生有效分块。"""


class DocumentIngestionService:
    """负责协调文件存储、解析、清洗、分块和数据库持久化。"""

    def __init__(
        self,
        session: AsyncSession,
        chunk_processor: ChunkProcessor,
        storage: LocalFileStorage | None = None,
        validator: UploadFileValidator | None = None,
        parser_registry: ParserRegistry | None = None,
        cleaner: DocumentCleaner | None = None,
        vector_index_service: VectorIndexService | None = None,
    ) -> None:
        """初始化文档导入服务及其依赖。"""
        if not isinstance(session, AsyncSession):
            raise TypeError("session 必须是 AsyncSession 类型")

        if not isinstance(chunk_processor, ChunkProcessor):
            raise TypeError("chunk_processor 必须是 ChunkProcessor 类型")

        if storage is not None and not isinstance(storage, LocalFileStorage):
            raise TypeError("storage 必须是 LocalFileStorage 类型")

        if validator is not None and not isinstance(validator, UploadFileValidator):
            raise TypeError("validator 必须是 UploadFileValidator 类型")

        if parser_registry is not None and not isinstance(parser_registry, ParserRegistry):
            raise TypeError("parser_registry 必须是 ParserRegistry 类型")

        if cleaner is not None and not isinstance(cleaner, DocumentCleaner):
            raise TypeError("cleaner 必须是 DocumentCleaner 类型")
        if vector_index_service is not None and not isinstance(
            vector_index_service, VectorIndexService
        ):
            raise TypeError("vector_index_service 必须是 VectorIndexService 类型")

        self.session = session
        self.document_service = DocumentService(session)
        self.chunk_repository = DocumentChunkRepository(session)

        self.storage = storage or LocalFileStorage()
        self.validator = validator or UploadFileValidator(
            max_size_bytes=get_settings().max_upload_size_bytes
        )
        self.parser_registry = parser_registry or ParserRegistry()
        self.cleaner = cleaner or DocumentCleaner()
        self.chunk_processor = chunk_processor
        self.vector_index_service = vector_index_service

    async def _store_and_validate_file(
        self,
        upload_file: UploadFile,
    ) -> tuple[StoredFile, ValidatedFile]:
        """保存上传文件并执行安全校验，失败时清理已保存文件。"""
        if not isinstance(upload_file, UploadFile):
            raise TypeError("upload_file 必须是 Starlette UploadFile 类型")

        stored_file = await self.storage.save(upload_file)

        try:
            validated_file = self.validator.validate(
                filename=stored_file.original_filename,
                file_path=stored_file.file_path,
                content_type=upload_file.content_type,
            )
        except BaseException as original_error:
            try:
                await self.storage.delete(stored_file.file_path)
            except Exception as cleanup_error:
                # 清理失败不能覆盖原始校验异常。
                original_error.add_note(f"清理校验失败的上传文件时发生异常：{cleanup_error!r}")

            raise

        return stored_file, validated_file

    async def _check_duplicate(
        self,
        knowledge_base_id: int,
        stored_file: StoredFile,
    ) -> None:
        """检查知识库内是否存在相同内容的文档，重复时清理新文件。"""
        duplicated = await self.document_service.get_by_content_hash(
            knowledge_base_id=knowledge_base_id,
            content_hash=stored_file.content_hash,
        )

        if duplicated is None:
            return

        duplicate_error = DocumentAlreadyExistsError(duplicated.id)

        try:
            await self.storage.delete(stored_file.file_path)
        except Exception as cleanup_error:
            # 清理失败不能覆盖重复文档异常。
            duplicate_error.add_note(f"清理重复上传文件时发生异常：{cleanup_error!r}")

        raise duplicate_error

    async def _prepare_upload(
        self,
        knowledge_base_id: int,
        upload_file: UploadFile,
    ) -> tuple[StoredFile, ValidatedFile]:
        """完成文件保存、安全校验和知识库内重复检查。"""
        stored_file, validated_file = await self._store_and_validate_file(upload_file)

        try:
            await self._check_duplicate(knowledge_base_id, stored_file)
        except DocumentAlreadyExistsError:
            # 重复文件的清理已经由 _check_duplicate() 负责。
            raise
        except BaseException as original_error:
            # 去重查询异常时清理文件，同时保留原始异常。
            try:
                await self.storage.delete(stored_file.file_path)
            except Exception as cleanup_error:
                original_error.add_note(f"清理去重检查失败的上传文件时发生异常：{cleanup_error!r}")
            raise

        return stored_file, validated_file

    async def _parse_document(
        self,
        stored_file: StoredFile,
        validated_file: ValidatedFile,
    ) -> ParsedDocument:
        """根据校验后的文件类型选择解析器并解析文档。"""
        parser = self.parser_registry.get_parser(validated_file.file_type)

        return await parser.parse(Path(stored_file.file_path))

    def _clean_document(
        self,
        parsed_document: ParsedDocument,
    ) -> ParsedDocument:
        """清洗解析结果，并拒绝没有有效文本的文档。"""
        if not isinstance(parsed_document, ParsedDocument):
            raise TypeError("parsed_document 必须是 ParsedDocument 类型")

        cleaned_content = self.cleaner.clean(parsed_document.content)

        if not cleaned_content.strip():
            raise EmptyDocumentContentError("文档清洗后没有有效文本内容")

        return replace(parsed_document, content=cleaned_content)

    def _chunk_document(
        self,
        cleaned_document: ParsedDocument,
    ) -> list[TextChunk]:
        """对清洗后的文档分块，并校验分块结果。"""
        if not isinstance(cleaned_document, ParsedDocument):
            raise TypeError("cleaned_document 必须是 ParsedDocument 类型")

        if cleaned_document.file_type == "md":
            chunks = self.chunk_processor.process(
                cleaned_document.content,
                markdown=True,
            )
        else:
            chunks = self.chunk_processor.process(cleaned_document.content)

        if not isinstance(chunks, list):
            raise TypeError("ChunkProcessor 必须返回 list[TextChunk]")

        if not chunks:
            raise EmptyDocumentChunksError("文档没有产生有效分块")

        for expected_index, chunk in enumerate(chunks):
            if not isinstance(chunk, TextChunk):
                raise TypeError("分块结果必须全部是 TextChunk 类型")

            if chunk.chunk_index != expected_index:
                raise ValueError("分块索引必须从 0 开始连续递增")

            if (
                chunk.start_index < 0
                or chunk.end_index > len(cleaned_document.content)
                or cleaned_document.content[chunk.start_index : chunk.end_index] != chunk.content
            ):
                raise ValueError("分块字符偏移量与原文不一致")

            if (
                isinstance(chunk.token_count, bool)
                or not isinstance(chunk.token_count, int)
                or chunk.token_count < 0
            ):
                raise ValueError("每个分块必须具有有效的 Token 数量")

        return chunks

    async def _process_document(
        self,
        stored_file: StoredFile,
        validated_file: ValidatedFile,
    ) -> tuple[ParsedDocument, list[TextChunk]]:
        "依次解析、清洗和分块文档。"
        parsed_document = await self._parse_document(
            stored_file,
            validated_file,
        )
        cleaned_document = self._clean_document(parsed_document)
        chunks = self._chunk_document(cleaned_document)
        return cleaned_document, chunks

    def _build_chunk_entities(
        self,
        document_id: int,
        chunks: list[TextChunk],
    ) -> list[DocumentChunk]:
        """将文本分块转换为数据库 ORM 对象。"""
        if isinstance(document_id, bool) or not isinstance(document_id, int):
            raise TypeError("document_id 必须是整数")

        if document_id <= 0:
            raise ValueError("document_id 必须大于 0")

        if not isinstance(chunks, list):
            raise TypeError("chunks 必须是列表")

        if not chunks:
            raise ValueError("chunks 不能为空")

        entities = []

        for chunk in chunks:
            if not isinstance(chunk, TextChunk):
                raise TypeError("chunks 中的元素必须是 TextChunk 类型")

            if (
                isinstance(chunk.token_count, bool)
                or not isinstance(chunk.token_count, int)
                or chunk.token_count < 0
            ):
                raise ValueError("分块必须具有有效的 Token 数量")

            if not isinstance(chunk.metadata, dict):
                raise TypeError("分块 metadata 必须是字典")

            entities.append(
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    start_index=chunk.start_index,
                    end_index=chunk.end_index,
                    chunk_metadata=dict(chunk.metadata),
                )
            )

        return entities

    async def _persist_chunks(
        self,
        document_id: int,
        chunks: list[TextChunk],
    ) -> list[DocumentChunk]:
        """将文档分块批量写入数据库，不提交事务。"""
        entities = self._build_chunk_entities(document_id, chunks)

        return await self.chunk_repository.create_many(entities)

    async def _commit_chunks(self) -> None:
        """提交分块事务；提交失败时回滚并保留原始异常。"""
        try:
            await self.session.commit()
        except BaseException as exc:
            try:
                await self.session.rollback()
            except BaseException as rollback_error:
                exc.add_note(f"分块事务回滚失败：{rollback_error}")
            raise

    async def _save_document_chunks(
        self,
        document_id: int,
        chunks: list[TextChunk],
    ) -> list[DocumentChunk]:
        """保存文档分块并提交事务；写入失败时回滚。"""
        try:
            persisted_chunks = await self._persist_chunks(document_id, chunks)
        except BaseException as original_error:
            try:
                await self.session.rollback()
            except BaseException as rollback_error:
                original_error.add_note(f"分块写入失败后的事务回滚异常：{rollback_error}")
            raise

        await self._commit_chunks()
        return persisted_chunks

    async def _mark_document_failed(
        self,
        document_id: int,
        original_error: BaseException,
    ) -> None:
        """将文档标记为失败，同时保留最初的处理异常。"""
        error_message = str(original_error).strip()

        if not error_message:
            error_message = f"{type(original_error).__name__}: 未提供错误详情"

        try:
            await self.document_service.update_status(
                document_id=document_id,
                status="failed",
                error_message=error_message,
            )
        except BaseException as status_error:
            original_error.add_note(f"文档状态更新失败：{status_error}")

    async def _save_document_chunks_safely(
        self,
        document_id: int,
        chunks: list[TextChunk],
    ) -> list[DocumentChunk]:
        """保存文档分块；失败时更新文档状态并保留原始异常。"""
        try:
            return await self._save_document_chunks(document_id, chunks)
        except Exception as original_error:
            try:
                await self._mark_document_failed(
                    document_id,
                    original_error,
                )
            except Exception as status_error:
                original_error.add_note(f"失败状态更新异常：{status_error}")
            raise

    async def _index_document_chunks_safely(
        self,
        document_id: int,
        knowledge_base_id: int,
        chunks: list[DocumentChunk],
    ) -> None:
        """建立文档向量索引；失败时保留分块并标记文档失败。"""
        if self.vector_index_service is None:
            return

        try:
            await self.vector_index_service.index_chunks(
                chunks=chunks,
                knowledge_base_id=knowledge_base_id,
            )
        except Exception as original_error:
            await self._mark_document_failed(document_id, original_error)
            raise

    async def _create_document_record(
        self,
        knowledge_base_id: int,
        stored_file: StoredFile,
        validated_file: ValidatedFile,
    ) -> Document:
        """创建文档元数据；失败后确认文件是否仍被数据库引用。"""
        try:
            return await self.document_service.create(
                knowledge_base_id=knowledge_base_id,
                name=stored_file.original_filename,
                file_type=validated_file.file_type,
                file_path=str(stored_file.file_path),
                file_size=stored_file.file_size,
                content_hash=stored_file.content_hash,
            )
        except Exception as original_error:
            # 创建异常不代表事务一定没有提交，先确认数据库引用情况。
            try:
                existing = await self.document_service.get_by_content_hash(
                    knowledge_base_id=knowledge_base_id,
                    content_hash=stored_file.content_hash,
                )
            except Exception as lookup_error:
                # 无法确认记录状态时保留文件，避免删除数据库正在引用的文件。
                original_error.add_note(
                    f"创建失败后的文档记录查询异常，已保留原始文件：{lookup_error!r}"
                )
                raise original_error from lookup_error

            if existing is not None and existing.file_path == str(stored_file.file_path):
                # 数据库已经引用当前文件，不能清理。
                original_error.add_note("数据库中已存在引用当前文件的文档记录，已保留原始文件。")
                raise

            try:
                await self.storage.delete(stored_file.file_path)
            except Exception as cleanup_error:
                original_error.add_note(f"创建文档记录失败后的文件清理异常：{cleanup_error!r}")
            raise

    async def ingest(
        self,
        knowledge_base_id: int,
        upload_file: UploadFile,
    ) -> Document:
        """执行完整文档导入流程并返回处理完成的文档。"""
        stored_file, validated_file = await self._prepare_upload(
            knowledge_base_id,
            upload_file,
        )

        # 文档记录创建前发生异常时，清理已经保存的原始文件。
        try:
            cleaned_document, chunks = await self._process_document(
                stored_file,
                validated_file,
            )
        except BaseException as original_error:
            try:
                await self.storage.delete(stored_file.file_path)
            except Exception as cleanup_error:
                original_error.add_note(f"文档处理失败后的原始文件清理异常：{cleanup_error!r}")
            raise

        # 此方法内部负责创建失败后的文件清理和数据库引用检查。
        document = await self._create_document_record(
            knowledge_base_id,
            stored_file,
            validated_file,
        )

        # 文档创建成功后进入 processing 状态。
        processing_document = await self.document_service.update_status(
            document_id=document.id,
            status="processing",
        )

        if processing_document is None:
            raise RuntimeError(f"文档记录不存在，无法开始处理：{document.id}")

        # 分块保存失败时保留原始文件和文档记录，并标记为 failed。
        persisted_chunks = await self._save_document_chunks_safely(
            document.id,
            chunks,
        )

        # SQLite 分块提交后建立向量索引，索引成功后才能完成导入。
        await self._index_document_chunks_safely(
            document_id=document.id,
            knowledge_base_id=knowledge_base_id,
            chunks=persisted_chunks,
        )

        # 最后更新状态。若提交后刷新失败，不删除可能已被数据库引用的文件。
        completed_document = await self.document_service.update_status(
            document_id=document.id,
            status="completed",
        )

        if completed_document is None:
            raise RuntimeError(f"文档记录不存在，无法完成导入：{document.id}")

        return completed_document
