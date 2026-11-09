"""KnowledgeFlow DocumentIngestionService 测试。"""

import asyncio

import pytest

from app.ingestion.chunk_processor import ChunkProcessor
from app.ingestion.chunker import TextChunker
from app.ingestion.cleaner import DocumentCleaner
from app.ingestion.parsers.registry import ParserRegistry
from app.ingestion.storage import LocalFileStorage, StoredFile
from app.ingestion.validators import UploadFileValidator
from app.repositories.document_chunk import DocumentChunkRepository
from app.services.document import DocumentService
from app.services.document_ingestion import (
    DocumentAlreadyExistsError,
    DocumentIngestionService,
    EmptyDocumentChunksError,
    EmptyDocumentContentError,
    KnowledgeBaseDeletingError,
    KnowledgeBaseNotFoundError,
)
from app.services.knowledge_base import KnowledgeBaseService


class FakeTokenCounter:
    """测试用 Token 计数器。"""

    def count(self, text: str) -> int:
        """返回确定性的测试计数结果。"""
        return len(text)


def create_chunk_processor() -> ChunkProcessor:
    """创建测试用分块处理器。"""
    return ChunkProcessor(
        chunker=TextChunker(),
        token_counter=FakeTokenCounter(),
    )


def test_service_initializes_with_default_dependencies(database):
    """测试默认依赖初始化及 Session 共享。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = DocumentIngestionService(
                session=session,
                chunk_processor=create_chunk_processor(),
            )

            assert service.session is session

            assert isinstance(service.document_service, DocumentService)
            assert service.document_service.session is session

            assert isinstance(service.chunk_repository, DocumentChunkRepository)
            assert service.chunk_repository.session is session

            assert isinstance(service.storage, LocalFileStorage)
            assert isinstance(service.validator, UploadFileValidator)
            assert isinstance(service.parser_registry, ParserRegistry)
            assert isinstance(service.cleaner, DocumentCleaner)
            assert isinstance(service.chunk_processor, ChunkProcessor)

    asyncio.run(run_test())


def test_service_accepts_injected_dependencies(database, tmp_path):
    """测试允许注入自定义依赖。"""
    _, session_factory = database

    storage = LocalFileStorage(upload_dir=tmp_path / "uploads")
    validator = UploadFileValidator(max_size_bytes=1024)
    parser_registry = ParserRegistry()
    cleaner = DocumentCleaner()
    chunk_processor = create_chunk_processor()

    async def run_test():
        async with session_factory() as session:
            service = DocumentIngestionService(
                session=session,
                chunk_processor=chunk_processor,
                storage=storage,
                validator=validator,
                parser_registry=parser_registry,
                cleaner=cleaner,
            )

            assert service.storage is storage
            assert service.validator is validator
            assert service.parser_registry is parser_registry
            assert service.cleaner is cleaner
            assert service.chunk_processor is chunk_processor

    asyncio.run(run_test())


def test_service_uses_configured_upload_limit(database):
    """测试默认校验器使用项目上传大小配置。"""
    from app.core.config import get_settings

    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            service = DocumentIngestionService(
                session=session,
                chunk_processor=create_chunk_processor(),
            )

            assert service.validator.max_size_bytes == get_settings().max_upload_size_bytes

    asyncio.run(run_test())


def test_service_rejects_invalid_session(database):
    """测试拒绝无效数据库会话。"""
    _, session_factory = database

    async def run_test():
        with pytest.raises(TypeError, match="session 必须是 AsyncSession"):
            DocumentIngestionService(
                session=object(),
                chunk_processor=create_chunk_processor(),
            )

    asyncio.run(run_test())


def test_service_rejects_invalid_chunk_processor(database):
    """测试拒绝无效分块处理器。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            with pytest.raises(TypeError, match="chunk_processor"):
                DocumentIngestionService(
                    session=session,
                    chunk_processor=object(),
                )

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("dependency_name", "dependency_value", "error"),
    [
        ("storage", object(), "storage"),
        ("validator", object(), "validator"),
        ("parser_registry", object(), "parser_registry"),
        ("cleaner", object(), "cleaner"),
    ],
)
def test_service_rejects_invalid_optional_dependencies(
    database,
    dependency_name,
    dependency_value,
    error,
):
    """测试拒绝无效的可选依赖。"""
    _, session_factory = database

    async def run_test():
        async with session_factory() as session:
            with pytest.raises(TypeError, match=error):
                DocumentIngestionService(
                    session=session,
                    chunk_processor=create_chunk_processor(),
                    **{dependency_name: dependency_value},
                )

    asyncio.run(run_test())


def make_upload_file(
    content: bytes,
    filename: str = "test.txt",
    content_type: str | None = "text/plain",
):
    """构造测试用 FastAPI 上传文件。"""
    import io

    from fastapi import UploadFile
    from starlette.datastructures import Headers

    headers = Headers({"content-type": content_type} if content_type is not None else {})

    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=headers,
    )


@pytest.mark.asyncio
async def test_store_and_validate_file_success(tmp_path):
    """测试保存并校验有效 TXT 文件。"""
    from pathlib import Path

    from app.ingestion.storage import LocalFileStorage
    from app.ingestion.validators import ValidatedFile

    storage = LocalFileStorage(
        upload_dir=tmp_path / "uploads",
        max_size_bytes=1024,
    )
    service = object.__new__(DocumentIngestionService)
    service.storage = storage
    service.validator = UploadFileValidator(max_size_bytes=1024)

    upload = make_upload_file("KnowledgeFlow 测试内容".encode())

    stored_file, validated_file = await service._store_and_validate_file(upload)

    assert isinstance(stored_file, StoredFile)
    assert isinstance(validated_file, ValidatedFile)
    assert stored_file.original_filename == "test.txt"
    assert validated_file.filename == "test.txt"
    assert validated_file.file_type == "txt"
    assert Path(stored_file.file_path).is_file()


@pytest.mark.asyncio
async def test_store_and_validate_file_deletes_file_when_validation_fails(
    tmp_path,
):
    """测试校验失败时删除已经保存的文件。"""

    from app.ingestion.storage import LocalFileStorage
    from app.ingestion.validators import FileValidationError

    storage = LocalFileStorage(
        upload_dir=tmp_path / "uploads",
        max_size_bytes=1024,
    )
    service = object.__new__(DocumentIngestionService)
    service.storage = storage
    service.validator = UploadFileValidator(max_size_bytes=1024)

    upload = make_upload_file(b"\xff\xfeinvalid utf8")

    with pytest.raises(FileValidationError, match="UTF-8"):
        await service._store_and_validate_file(upload)

    saved_files = list((tmp_path / "uploads").glob("*.txt"))
    assert saved_files == []
    assert all(path.is_file() for path in saved_files) is True


@pytest.mark.asyncio
async def test_store_and_validate_file_passes_original_filename_and_mime(
    tmp_path,
):
    """测试校验器收到原始文件名和客户端 MIME 类型。"""
    from app.ingestion.storage import LocalFileStorage
    from app.ingestion.validators import FileValidationError

    storage = LocalFileStorage(
        upload_dir=tmp_path / "uploads",
        max_size_bytes=1024,
    )
    service = object.__new__(DocumentIngestionService)
    service.storage = storage
    service.validator = UploadFileValidator(max_size_bytes=1024)

    upload = make_upload_file(
        b"valid text",
        filename="original.txt",
        content_type="application/pdf",
    )

    with pytest.raises(FileValidationError, match="MIME 类型"):
        await service._store_and_validate_file(upload)

    assert list((tmp_path / "uploads").iterdir()) == []


@pytest.mark.asyncio
async def test_store_and_validate_file_preserves_validation_error_if_cleanup_fails(
    tmp_path,
    monkeypatch,
):
    """测试文件清理失败时仍保留原始校验异常。"""
    from app.ingestion.storage import LocalFileStorage
    from app.ingestion.validators import FileValidationError

    storage = LocalFileStorage(
        upload_dir=tmp_path / "uploads",
        max_size_bytes=1024,
    )
    service = object.__new__(DocumentIngestionService)
    service.storage = storage
    service.validator = UploadFileValidator(max_size_bytes=1024)

    async def fail_delete(file_path):
        raise OSError("模拟磁盘删除失败")

    monkeypatch.setattr(storage, "delete", fail_delete)

    upload = make_upload_file(b"\xffinvalid utf8")

    with pytest.raises(FileValidationError, match="UTF-8") as exc_info:
        await service._store_and_validate_file(upload)

    assert any("模拟磁盘删除失败" in note for note in getattr(exc_info.value, "__notes__", []))


@pytest.mark.asyncio
async def test_store_and_validate_file_rejects_invalid_upload_object(
    tmp_path,
):
    """测试拒绝非 UploadFile 对象。"""
    from app.ingestion.storage import LocalFileStorage

    service = object.__new__(DocumentIngestionService)
    service.storage = LocalFileStorage(
        upload_dir=tmp_path / "uploads",
        max_size_bytes=1024,
    )
    service.validator = UploadFileValidator(max_size_bytes=1024)

    with pytest.raises(TypeError, match="UploadFile"):
        await service._store_and_validate_file(b"invalid")


@pytest.mark.asyncio
async def test_check_duplicate_keeps_file_when_document_does_not_exist(
    tmp_path,
    monkeypatch,
):
    """测试没有重复文档时保留上传文件。"""

    service = object.__new__(DocumentIngestionService)

    stored_file = StoredFile(
        file_path=str(tmp_path / "test.txt"),
        file_size=10,
        content_hash="a" * 64,
        original_filename="test.txt",
    )

    async def get_by_content_hash(knowledge_base_id, content_hash):
        assert knowledge_base_id == 1
        assert content_hash == "a" * 64
        return None

    async def fail_delete(file_path):
        raise AssertionError("没有重复文档时不应该删除文件")

    service.document_service = type(
        "FakeDocumentService",
        (),
        {"get_by_content_hash": staticmethod(get_by_content_hash)},
    )()

    service.storage = type(
        "FakeStorage",
        (),
        {"delete": staticmethod(fail_delete)},
    )()

    await service._check_duplicate(1, stored_file)


@pytest.mark.asyncio
async def test_check_duplicate_deletes_file_and_raises_error(
    tmp_path,
):
    """测试发现重复文档时删除新文件并抛出异常。"""
    from types import SimpleNamespace

    service = object.__new__(DocumentIngestionService)

    file_path = tmp_path / "duplicate.txt"
    file_path.write_text("重复内容", encoding="utf-8")

    stored_file = StoredFile(
        file_path=str(file_path),
        file_size=file_path.stat().st_size,
        content_hash="b" * 64,
        original_filename="duplicate.txt",
    )

    async def get_by_content_hash(knowledge_base_id, content_hash):
        assert knowledge_base_id == 2
        assert content_hash == "b" * 64
        return SimpleNamespace(id=123)

    service.document_service = SimpleNamespace(
        get_by_content_hash=get_by_content_hash,
    )
    service.storage = LocalFileStorage(upload_dir=tmp_path)

    with pytest.raises(DocumentAlreadyExistsError) as exc_info:
        await service._check_duplicate(2, stored_file)

    assert exc_info.value.document_id == 123
    assert "123" in str(exc_info.value)
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_check_duplicate_preserves_error_when_cleanup_fails(
    monkeypatch,
):
    """测试重复文件清理失败时保留原始重复异常。"""
    from types import SimpleNamespace

    service = object.__new__(DocumentIngestionService)

    stored_file = StoredFile(
        file_path="/tmp/duplicate.txt",
        file_size=10,
        content_hash="c" * 64,
        original_filename="duplicate.txt",
    )

    async def get_by_content_hash(knowledge_base_id, content_hash):
        return SimpleNamespace(id=456)

    async def fail_delete(file_path):
        raise OSError("模拟文件删除失败")

    service.document_service = SimpleNamespace(
        get_by_content_hash=get_by_content_hash,
    )
    service.storage = SimpleNamespace(delete=fail_delete)

    with pytest.raises(DocumentAlreadyExistsError) as exc_info:
        await service._check_duplicate(1, stored_file)

    assert exc_info.value.document_id == 456
    assert any("模拟文件删除失败" in note for note in getattr(exc_info.value, "__notes__", []))


@pytest.mark.asyncio
async def test_prepare_upload_success(tmp_path):
    """测试文件保存、校验和去重检查全部成功。"""
    from pathlib import Path
    from types import SimpleNamespace

    from app.ingestion.storage import StoredFile
    from app.ingestion.validators import ValidatedFile

    storage = LocalFileStorage(
        upload_dir=tmp_path / "uploads",
        max_size_bytes=1024,
    )
    service = object.__new__(DocumentIngestionService)
    service.storage = storage
    service.validator = UploadFileValidator(max_size_bytes=1024)

    async def get_by_content_hash(knowledge_base_id, content_hash):
        assert knowledge_base_id == 1
        assert len(content_hash) == 64
        return None

    service.document_service = SimpleNamespace(
        get_by_content_hash=get_by_content_hash,
    )

    stored_file, validated_file = await service._prepare_upload(
        1,
        make_upload_file("KnowledgeFlow 测试内容".encode()),
    )

    assert isinstance(stored_file, StoredFile)
    assert isinstance(validated_file, ValidatedFile)
    assert stored_file.original_filename == "test.txt"
    assert validated_file.file_type == "txt"
    assert Path(stored_file.file_path).is_file()


@pytest.mark.asyncio
async def test_prepare_upload_duplicate_cleans_file_once(tmp_path):
    """测试发现重复文件时清理新文件且不重复清理。"""
    from types import SimpleNamespace

    storage = LocalFileStorage(
        upload_dir=tmp_path / "uploads",
        max_size_bytes=1024,
    )
    service = object.__new__(DocumentIngestionService)
    service.storage = storage
    service.validator = UploadFileValidator(max_size_bytes=1024)

    delete_calls = []
    original_delete = storage.delete

    async def track_delete(file_path):
        delete_calls.append(file_path)
        return await original_delete(file_path)

    storage.delete = track_delete

    async def get_by_content_hash(knowledge_base_id, content_hash):
        return SimpleNamespace(id=789)

    service.document_service = SimpleNamespace(
        get_by_content_hash=get_by_content_hash,
    )

    with pytest.raises(DocumentAlreadyExistsError) as exc_info:
        await service._prepare_upload(
            1,
            make_upload_file("重复内容".encode()),
        )

    assert exc_info.value.document_id == 789
    assert len(delete_calls) == 1
    assert list((tmp_path / "uploads").iterdir()) == []


@pytest.mark.asyncio
async def test_prepare_upload_cleans_file_when_duplicate_query_fails(
    tmp_path,
):
    """测试去重查询异常时清理已保存文件并保留原始异常。"""
    from types import SimpleNamespace

    storage = LocalFileStorage(
        upload_dir=tmp_path / "uploads",
        max_size_bytes=1024,
    )
    service = object.__new__(DocumentIngestionService)
    service.storage = storage
    service.validator = UploadFileValidator(max_size_bytes=1024)

    async def get_by_content_hash(knowledge_base_id, content_hash):
        raise RuntimeError("模拟数据库查询失败")

    service.document_service = SimpleNamespace(
        get_by_content_hash=get_by_content_hash,
    )

    with pytest.raises(RuntimeError, match="模拟数据库查询失败"):
        await service._prepare_upload(
            1,
            make_upload_file("数据库异常测试".encode()),
        )

    assert list((tmp_path / "uploads").iterdir()) == []


@pytest.mark.asyncio
async def test_prepare_upload_preserves_query_error_when_cleanup_fails(
    tmp_path,
    monkeypatch,
):
    """测试去重查询和文件清理均失败时保留查询异常。"""
    from types import SimpleNamespace

    storage = LocalFileStorage(
        upload_dir=tmp_path / "uploads",
        max_size_bytes=1024,
    )
    service = object.__new__(DocumentIngestionService)
    service.storage = storage
    service.validator = UploadFileValidator(max_size_bytes=1024)

    async def get_by_content_hash(knowledge_base_id, content_hash):
        raise RuntimeError("原始数据库异常")

    async def fail_delete(file_path):
        raise OSError("模拟文件清理失败")

    service.document_service = SimpleNamespace(
        get_by_content_hash=get_by_content_hash,
    )
    monkeypatch.setattr(storage, "delete", fail_delete)

    with pytest.raises(RuntimeError, match="原始数据库异常") as exc_info:
        await service._prepare_upload(
            1,
            make_upload_file("清理异常测试".encode()),
        )

    assert any("模拟文件清理失败" in note for note in getattr(exc_info.value, "__notes__", []))


@pytest.mark.asyncio
async def test_parse_document_success(tmp_path):
    """测试根据校验后的文件类型成功解析 TXT 文档。"""

    from app.ingestion.parsers.base import ParsedDocument
    from app.ingestion.parsers.registry import ParserRegistry
    from app.ingestion.storage import StoredFile
    from app.ingestion.validators import ValidatedFile

    file_path = tmp_path / "document.txt"
    file_path.write_text("KnowledgeFlow 文档解析测试", encoding="utf-8")

    service = object.__new__(DocumentIngestionService)
    service.parser_registry = ParserRegistry()

    stored_file = StoredFile(
        file_path=str(file_path),
        file_size=file_path.stat().st_size,
        content_hash="a" * 64,
        original_filename="document.txt",
    )
    validated_file = ValidatedFile(
        filename="document.txt",
        file_type="txt",
        file_size=file_path.stat().st_size,
        content_type="text/plain",
    )

    result = await service._parse_document(stored_file, validated_file)

    assert isinstance(result, ParsedDocument)
    assert result.file_type == "txt"
    assert result.content == "KnowledgeFlow 文档解析测试"
    assert result.metadata["encoding"] == "utf-8-sig"


@pytest.mark.asyncio
async def test_parse_document_rejects_unsupported_file_type(tmp_path):
    """测试不支持的文件类型无法获取解析器。"""
    from app.ingestion.parsers.base import UnsupportedFileTypeError
    from app.ingestion.parsers.registry import ParserRegistry
    from app.ingestion.storage import StoredFile
    from app.ingestion.validators import ValidatedFile

    service = object.__new__(DocumentIngestionService)
    service.parser_registry = ParserRegistry()

    stored_file = StoredFile(
        file_path=str(tmp_path / "document.xyz"),
        file_size=10,
        content_hash="b" * 64,
        original_filename="document.xyz",
    )
    validated_file = ValidatedFile(
        filename="document.xyz",
        file_type="xyz",
        file_size=10,
        content_type="application/octet-stream",
    )

    with pytest.raises(UnsupportedFileTypeError):
        await service._parse_document(stored_file, validated_file)


@pytest.mark.asyncio
async def test_parse_document_preserves_parser_error(tmp_path):
    """测试解析器异常能够原样向上传递。"""
    from app.ingestion.parsers.base import DocumentParseError
    from app.ingestion.storage import StoredFile
    from app.ingestion.validators import ValidatedFile

    class FailingParser:
        async def parse(self, file_path):
            raise DocumentParseError("模拟文档解析失败")

    class FakeParserRegistry:
        def get_parser(self, extension):
            assert extension == "txt"
            return FailingParser()

    file_path = tmp_path / "document.txt"
    file_path.write_text("测试内容", encoding="utf-8")

    service = object.__new__(DocumentIngestionService)
    service.parser_registry = FakeParserRegistry()

    stored_file = StoredFile(
        file_path=str(file_path),
        file_size=file_path.stat().st_size,
        content_hash="c" * 64,
        original_filename="document.txt",
    )
    validated_file = ValidatedFile(
        filename="document.txt",
        file_type="txt",
        file_size=file_path.stat().st_size,
        content_type="text/plain",
    )

    with pytest.raises(DocumentParseError, match="模拟文档解析失败"):
        await service._parse_document(stored_file, validated_file)


def test_clean_document_success():
    """测试成功清洗文本并保留解析元数据和警告。"""
    from app.ingestion.parsers.base import ParsedDocument

    service = object.__new__(DocumentIngestionService)
    service.cleaner = DocumentCleaner()

    parsed_document = ParsedDocument(
        content="\n\n# KnowledgeFlow  \r\n\r\n正文内容\x00  \n",
        file_type="md",
        metadata={
            "page_count": 2,
            "source": "test",
        },
        warnings=("测试解析警告",),
    )

    result = service._clean_document(parsed_document)

    assert result.content == "# KnowledgeFlow\n\n正文内容"
    assert result.file_type == "md"
    assert result.metadata == parsed_document.metadata
    assert result.warnings == parsed_document.warnings

    # 验证没有修改原始解析结果。
    assert result is not parsed_document
    assert parsed_document.content != result.content


def test_clean_document_rejects_empty_content():
    """测试清洗后内容为空时抛出明确异常。"""
    from app.ingestion.parsers.base import ParsedDocument
    from app.services.document_ingestion import EmptyDocumentContentError

    service = object.__new__(DocumentIngestionService)
    service.cleaner = DocumentCleaner()

    parsed_document = ParsedDocument(
        content="",
        file_type="txt",
    )

    with pytest.raises(
        EmptyDocumentContentError,
        match="没有有效文本内容",
    ):
        service._clean_document(parsed_document)


@pytest.mark.parametrize(
    "content",
    [
        "   ",
        "\t\n\n\t",
        "\x00\x01\x02",
        "\r\n\n  \r\n",
    ],
)
def test_clean_document_rejects_whitespace_or_control_only_content(content):
    """测试只有空白字符或控制字符的文档不能进入后续流程。"""
    from app.ingestion.parsers.base import ParsedDocument
    from app.services.document_ingestion import EmptyDocumentContentError

    service = object.__new__(DocumentIngestionService)
    service.cleaner = DocumentCleaner()

    parsed_document = ParsedDocument(
        content=content,
        file_type="txt",
    )

    with pytest.raises(EmptyDocumentContentError):
        service._clean_document(parsed_document)


def test_clean_document_rejects_invalid_input():
    """测试拒绝非 ParsedDocument 输入。"""
    service = object.__new__(DocumentIngestionService)
    service.cleaner = DocumentCleaner()

    with pytest.raises(TypeError, match="ParsedDocument"):
        service._clean_document("普通字符串")


def test_chunk_document_success():
    """测试成功分块并保留原文偏移量和 Token 数量。"""
    from app.ingestion.chunker import TextChunk
    from app.ingestion.parsers.base import ParsedDocument

    content = "KnowledgeFlow 第一段内容。KnowledgeFlow 第二段内容。"

    chunks = [
        TextChunk(
            chunk_index=0,
            content=content[:20],
            start_index=0,
            end_index=20,
            token_count=8,
        ),
        TextChunk(
            chunk_index=1,
            content=content[15:],
            start_index=15,
            end_index=len(content),
            token_count=9,
        ),
    ]

    class FakeChunkProcessor:
        def process(self, text):
            assert text == content
            return chunks

    service = object.__new__(DocumentIngestionService)
    service.chunk_processor = FakeChunkProcessor()

    document = ParsedDocument(
        content=content,
        file_type="txt",
    )

    result = service._chunk_document(document)

    assert result == chunks
    assert result[0].chunk_index == 0
    assert result[1].chunk_index == 1

    for chunk in result:
        assert content[chunk.start_index : chunk.end_index] == chunk.content
        assert isinstance(chunk.token_count, int)


def test_chunk_document_rejects_empty_chunks():
    """测试分块结果为空时抛出明确异常。"""
    from app.ingestion.parsers.base import ParsedDocument
    from app.services.document_ingestion import EmptyDocumentChunksError

    class FakeChunkProcessor:
        def process(self, text):
            return []

    service = object.__new__(DocumentIngestionService)
    service.chunk_processor = FakeChunkProcessor()

    document = ParsedDocument(
        content="有效文本",
        file_type="txt",
    )

    with pytest.raises(EmptyDocumentChunksError):
        service._chunk_document(document)


def test_chunk_document_rejects_invalid_input():
    """测试拒绝非 ParsedDocument 输入。"""
    service = object.__new__(DocumentIngestionService)

    with pytest.raises(TypeError, match="ParsedDocument"):
        service._chunk_document("普通字符串")


def test_chunk_document_rejects_non_text_chunk():
    """测试拒绝不符合 TextChunk 类型约束的结果。"""
    from app.ingestion.parsers.base import ParsedDocument

    class FakeChunkProcessor:
        def process(self, text):
            return ["不是 TextChunk"]

    service = object.__new__(DocumentIngestionService)
    service.chunk_processor = FakeChunkProcessor()

    document = ParsedDocument(
        content="有效文本",
        file_type="txt",
    )

    with pytest.raises(TypeError, match="TextChunk"):
        service._chunk_document(document)


def test_chunk_document_rejects_non_contiguous_indexes():
    """测试分块索引必须从零开始连续递增。"""
    from app.ingestion.chunker import TextChunk
    from app.ingestion.parsers.base import ParsedDocument

    class FakeChunkProcessor:
        def process(self, text):
            return [
                TextChunk(
                    chunk_index=1,
                    content=text,
                    start_index=0,
                    end_index=len(text),
                    token_count=2,
                )
            ]

    service = object.__new__(DocumentIngestionService)
    service.chunk_processor = FakeChunkProcessor()

    document = ParsedDocument(
        content="有效文本",
        file_type="txt",
    )

    with pytest.raises(ValueError, match="连续递增"):
        service._chunk_document(document)


def test_chunk_document_rejects_incorrect_offsets():
    """测试分块字符偏移量必须对应清洗后的原文。"""
    from app.ingestion.chunker import TextChunk
    from app.ingestion.parsers.base import ParsedDocument

    class FakeChunkProcessor:
        def process(self, text):
            return [
                TextChunk(
                    chunk_index=0,
                    content="错误文本",
                    start_index=0,
                    end_index=4,
                    token_count=2,
                )
            ]

    service = object.__new__(DocumentIngestionService)
    service.chunk_processor = FakeChunkProcessor()

    document = ParsedDocument(
        content="有效文本",
        file_type="txt",
    )

    with pytest.raises(ValueError, match="偏移量"):
        service._chunk_document(document)


def test_chunk_document_rejects_missing_token_count():
    """测试拒绝没有完成 Token 计数的分块。"""
    from app.ingestion.chunker import TextChunk
    from app.ingestion.parsers.base import ParsedDocument

    class FakeChunkProcessor:
        def process(self, text):
            return [
                TextChunk(
                    chunk_index=0,
                    content=text,
                    start_index=0,
                    end_index=len(text),
                    token_count=None,
                )
            ]

    service = object.__new__(DocumentIngestionService)
    service.chunk_processor = FakeChunkProcessor()

    document = ParsedDocument(
        content="有效文本",
        file_type="txt",
    )

    with pytest.raises(ValueError, match="Token"):
        service._chunk_document(document)


def test_chunk_document_preserves_processor_error():
    """测试 Token 计数失败时保留原始异常。"""
    from app.ingestion.parsers.base import ParsedDocument
    from app.ingestion.token_counter import TokenCounterError

    class FakeChunkProcessor:
        def process(self, text):
            raise TokenCounterError("模拟 Token 计数失败")

    service = object.__new__(DocumentIngestionService)
    service.chunk_processor = FakeChunkProcessor()

    document = ParsedDocument(
        content="有效文本",
        file_type="txt",
    )

    with pytest.raises(TokenCounterError, match="模拟 Token 计数失败"):
        service._chunk_document(document)


@pytest.mark.asyncio
async def test_process_document_success_and_call_order(monkeypatch):
    """测试解析、清洗、分块按顺序执行并返回完整结果。"""
    from app.ingestion.chunker import TextChunk
    from app.ingestion.parsers.base import ParsedDocument

    service = object.__new__(DocumentIngestionService)
    calls = []

    parsed_document = ParsedDocument(
        content="原始文本  \n\n第二段内容。",
        file_type="txt",
        metadata={"source": "test"},
    )
    cleaned_document = ParsedDocument(
        content="原始文本\n\n第二段内容。",
        file_type="txt",
        metadata={"source": "test"},
    )
    chunks = [
        TextChunk(
            chunk_index=0,
            content=cleaned_document.content,
            start_index=0,
            end_index=len(cleaned_document.content),
            token_count=8,
        )
    ]

    async def fake_parse(stored_file, validated_file):
        calls.append("parse")
        return parsed_document

    def fake_clean(document):
        calls.append("clean")
        assert document is parsed_document
        return cleaned_document

    def fake_chunk(document):
        calls.append("chunk")
        assert document is cleaned_document
        return chunks

    monkeypatch.setattr(service, "_parse_document", fake_parse)
    monkeypatch.setattr(service, "_clean_document", fake_clean)
    monkeypatch.setattr(service, "_chunk_document", fake_chunk)

    result_document, result_chunks = await service._process_document(
        object(),
        object(),
    )

    assert calls == ["parse", "clean", "chunk"]
    assert result_document is cleaned_document
    assert result_chunks == chunks


@pytest.mark.asyncio
async def test_process_document_stops_when_parsing_fails(monkeypatch):
    """测试解析失败后不再执行清洗和分块。"""
    from app.ingestion.parsers.base import DocumentParseError

    service = object.__new__(DocumentIngestionService)
    calls = []

    async def fake_parse(stored_file, validated_file):
        calls.append("parse")
        raise DocumentParseError("模拟解析失败")

    def fake_clean(document):
        calls.append("clean")
        raise AssertionError("解析失败后不应执行清洗")

    def fake_chunk(document):
        calls.append("chunk")
        raise AssertionError("解析失败后不应执行分块")

    monkeypatch.setattr(service, "_parse_document", fake_parse)
    monkeypatch.setattr(service, "_clean_document", fake_clean)
    monkeypatch.setattr(service, "_chunk_document", fake_chunk)

    with pytest.raises(DocumentParseError, match="模拟解析失败"):
        await service._process_document(object(), object())

    assert calls == ["parse"]


@pytest.mark.asyncio
async def test_process_document_stops_when_cleaning_fails(monkeypatch):
    """测试清洗失败后不再执行分块。"""
    from app.ingestion.parsers.base import ParsedDocument

    service = object.__new__(DocumentIngestionService)
    calls = []

    parsed_document = ParsedDocument(
        content="测试文本",
        file_type="txt",
    )

    async def fake_parse(stored_file, validated_file):
        calls.append("parse")
        return parsed_document

    def fake_clean(document):
        calls.append("clean")
        raise EmptyDocumentContentError("模拟清洗失败")

    def fake_chunk(document):
        calls.append("chunk")
        raise AssertionError("清洗失败后不应执行分块")

    monkeypatch.setattr(service, "_parse_document", fake_parse)
    monkeypatch.setattr(service, "_clean_document", fake_clean)
    monkeypatch.setattr(service, "_chunk_document", fake_chunk)

    with pytest.raises(EmptyDocumentContentError, match="模拟清洗失败"):
        await service._process_document(object(), object())

    assert calls == ["parse", "clean"]


@pytest.mark.asyncio
async def test_process_document_preserves_chunking_error(monkeypatch):
    """测试分块失败时保留原始异常。"""
    from app.ingestion.parsers.base import ParsedDocument

    service = object.__new__(DocumentIngestionService)
    calls = []

    parsed_document = ParsedDocument(
        content="测试文本",
        file_type="txt",
    )

    async def fake_parse(stored_file, validated_file):
        calls.append("parse")
        return parsed_document

    def fake_clean(document):
        calls.append("clean")
        return document

    def fake_chunk(document):
        calls.append("chunk")
        raise EmptyDocumentChunksError("模拟分块失败")

    monkeypatch.setattr(service, "_parse_document", fake_parse)
    monkeypatch.setattr(service, "_clean_document", fake_clean)
    monkeypatch.setattr(service, "_chunk_document", fake_chunk)

    with pytest.raises(EmptyDocumentChunksError, match="模拟分块失败"):
        await service._process_document(object(), object())

    assert calls == ["parse", "clean", "chunk"]


@pytest.mark.asyncio
async def test_process_document_rejects_invalid_parser_result(monkeypatch):
    """测试解析器返回非法结果时由清洗阶段拒绝。"""
    service = object.__new__(DocumentIngestionService)
    calls = []
    original_clean = DocumentIngestionService._clean_document

    async def fake_parse(stored_file, validated_file):
        calls.append("parse")
        return "不是 ParsedDocument"

    def fake_clean(document):
        calls.append("clean")
        return original_clean(service, document)

    def fake_chunk(document):
        calls.append("chunk")
        raise AssertionError("非法解析结果不应进入分块")

    monkeypatch.setattr(service, "_parse_document", fake_parse)
    monkeypatch.setattr(service, "_clean_document", fake_clean)
    monkeypatch.setattr(service, "_chunk_document", fake_chunk)

    with pytest.raises(TypeError, match="ParsedDocument"):
        await service._process_document(object(), object())

    assert calls == ["parse", "clean"]


def test_build_chunk_entities_success():
    """测试成功将 TextChunk 映射为 DocumentChunk。"""
    from app.ingestion.chunker import TextChunk
    from app.models import DocumentChunk

    service = object.__new__(DocumentIngestionService)

    metadata = {"source": "test", "page": 1}
    chunks = [
        TextChunk(
            chunk_index=0,
            content="第一段测试文本",
            start_index=0,
            end_index=7,
            token_count=5,
            metadata=metadata,
        ),
        TextChunk(
            chunk_index=1,
            content="第二段测试文本",
            start_index=7,
            end_index=14,
            token_count=6,
            metadata={"source": "test", "page": 2},
        ),
    ]

    entities = service._build_chunk_entities(123, chunks)

    assert len(entities) == 2
    assert all(isinstance(item, DocumentChunk) for item in entities)

    assert entities[0].document_id == 123
    assert entities[0].chunk_index == 0
    assert entities[0].content == "第一段测试文本"
    assert entities[0].token_count == 5
    assert entities[0].start_index == 0
    assert entities[0].end_index == 7
    assert entities[0].chunk_metadata == metadata

    assert entities[1].document_id == 123
    assert entities[1].chunk_index == 1
    assert entities[1].chunk_metadata["page"] == 2

    # ORM 元数据必须与原始分块元数据相互独立。
    assert entities[0].chunk_metadata is not chunks[0].metadata
    entities[0].chunk_metadata["new_key"] = "new_value"
    assert "new_key" not in chunks[0].metadata


def test_build_chunk_entities_rejects_invalid_document_id():
    """测试拒绝非法文档 ID。"""
    service = object.__new__(DocumentIngestionService)

    with pytest.raises(TypeError, match="document_id"):
        service._build_chunk_entities(True, [])

    with pytest.raises(TypeError, match="document_id"):
        service._build_chunk_entities("123", [])

    with pytest.raises(ValueError, match="大于 0"):
        service._build_chunk_entities(0, [])


def test_build_chunk_entities_rejects_invalid_chunks():
    """测试拒绝非法分块列表。"""
    service = object.__new__(DocumentIngestionService)

    with pytest.raises(TypeError, match="列表"):
        service._build_chunk_entities(1, "不是列表")

    with pytest.raises(ValueError, match="不能为空"):
        service._build_chunk_entities(1, [])


def test_build_chunk_entities_rejects_non_text_chunk():
    """测试拒绝非 TextChunk 对象。"""
    service = object.__new__(DocumentIngestionService)

    with pytest.raises(TypeError, match="TextChunk"):
        service._build_chunk_entities(1, ["非法分块"])


@pytest.mark.asyncio
async def test_persist_chunks_success(monkeypatch):
    """测试分块实体转换后成功调用 Repository 批量写入。"""
    service = object.__new__(DocumentIngestionService)

    chunks = [object(), object()]
    entities = [object(), object()]
    persisted_entities = [object(), object()]
    calls = []

    def fake_build(document_id, input_chunks):
        calls.append(("build", document_id, input_chunks))
        return entities

    class FakeChunkRepository:
        async def create_many(self, input_entities):
            calls.append(("create_many", input_entities))
            return persisted_entities

    service.chunk_repository = FakeChunkRepository()

    monkeypatch.setattr(service, "_build_chunk_entities", fake_build)

    result = await service._persist_chunks(123, chunks)

    assert result is persisted_entities
    assert calls == [
        ("build", 123, chunks),
        ("create_many", entities),
    ]


@pytest.mark.asyncio
async def test_persist_chunks_preserves_build_error(monkeypatch):
    """测试实体转换失败时不调用 Repository，并保留原始异常。"""
    service = object.__new__(DocumentIngestionService)
    calls = []

    def fake_build(document_id, chunks):
        calls.append("build")
        raise ValueError("模拟实体转换失败")

    class FakeChunkRepository:
        async def create_many(self, entities):
            calls.append("create_many")
            raise AssertionError("转换失败后不应执行批量写入")

    service.chunk_repository = FakeChunkRepository()

    monkeypatch.setattr(service, "_build_chunk_entities", fake_build)

    with pytest.raises(ValueError, match="模拟实体转换失败"):
        await service._persist_chunks(123, [object()])

    assert calls == ["build"]


@pytest.mark.asyncio
async def test_persist_chunks_preserves_repository_error(monkeypatch):
    """测试 Repository 写入失败时保留原始异常。"""
    service = object.__new__(DocumentIngestionService)
    calls = []

    entities = [object()]

    def fake_build(document_id, chunks):
        calls.append("build")
        return entities

    class FakeChunkRepository:
        async def create_many(self, input_entities):
            calls.append("create_many")
            assert input_entities is entities
            raise RuntimeError("模拟数据库写入失败")

    service.chunk_repository = FakeChunkRepository()

    monkeypatch.setattr(service, "_build_chunk_entities", fake_build)

    with pytest.raises(RuntimeError, match="模拟数据库写入失败"):
        await service._persist_chunks(123, [object()])

    assert calls == ["build", "create_many"]


@pytest.mark.asyncio
async def test_commit_chunks_success():
    """测试分块事务正常提交。"""
    service = object.__new__(DocumentIngestionService)
    calls = []

    class FakeSession:
        async def commit(self):
            calls.append("commit")

        async def rollback(self):
            calls.append("rollback")

    service.session = FakeSession()

    await service._commit_chunks()

    assert calls == ["commit"]


@pytest.mark.asyncio
async def test_commit_chunks_rolls_back_on_commit_error():
    """测试事务提交失败后执行回滚，并保留提交异常。"""
    service = object.__new__(DocumentIngestionService)
    calls = []
    commit_error = RuntimeError("模拟事务提交失败")

    class FakeSession:
        async def commit(self):
            calls.append("commit")
            raise commit_error

        async def rollback(self):
            calls.append("rollback")

    service.session = FakeSession()

    with pytest.raises(RuntimeError, match="模拟事务提交失败") as exc_info:
        await service._commit_chunks()

    assert exc_info.value is commit_error
    assert calls == ["commit", "rollback"]


@pytest.mark.asyncio
async def test_commit_chunks_preserves_commit_error_when_rollback_fails():
    """测试回滚也失败时，仍然保留最初的提交异常。"""
    service = object.__new__(DocumentIngestionService)
    calls = []
    commit_error = RuntimeError("原始提交异常")

    class FakeSession:
        async def commit(self):
            calls.append("commit")
            raise commit_error

        async def rollback(self):
            calls.append("rollback")
            raise OSError("模拟回滚失败")

    service.session = FakeSession()

    with pytest.raises(RuntimeError, match="原始提交异常") as exc_info:
        await service._commit_chunks()

    assert exc_info.value is commit_error
    assert calls == ["commit", "rollback"]
    assert any("回滚失败" in note for note in exc_info.value.__notes__)


@pytest.mark.asyncio
async def test_save_document_chunks_success(monkeypatch):
    """测试分块写入和事务提交成功。"""
    service = object.__new__(DocumentIngestionService)

    chunks = [object(), object()]
    persisted_chunks = [object(), object()]
    calls = []

    async def fake_persist(document_id, input_chunks):
        calls.append(("persist", document_id, input_chunks))
        return persisted_chunks

    async def fake_commit():
        calls.append(("commit",))

    monkeypatch.setattr(service, "_persist_chunks", fake_persist)
    monkeypatch.setattr(service, "_commit_chunks", fake_commit)

    result = await service._save_document_chunks(123, chunks)

    assert result is persisted_chunks
    assert calls == [
        ("persist", 123, chunks),
        ("commit",),
    ]


@pytest.mark.asyncio
async def test_save_document_chunks_preserves_persist_error(monkeypatch):
    """测试分块写入失败时回滚事务并保留原始异常。"""
    service = object.__new__(DocumentIngestionService)

    calls = []
    persist_error = RuntimeError("模拟分块写入失败")

    class FakeSession:
        async def rollback(self):
            calls.append("rollback")

    service.session = FakeSession()

    async def fake_persist(document_id, chunks):
        calls.append("persist")
        raise persist_error

    async def fake_commit():
        calls.append("commit")

    monkeypatch.setattr(service, "_persist_chunks", fake_persist)
    monkeypatch.setattr(service, "_commit_chunks", fake_commit)

    with pytest.raises(RuntimeError, match="模拟分块写入失败") as exc_info:
        await service._save_document_chunks(123, [object()])

    assert exc_info.value is persist_error
    assert calls == ["persist", "rollback"]


@pytest.mark.asyncio
async def test_save_document_chunks_preserves_commit_error(monkeypatch):
    """测试事务提交失败时向上层传播原始异常。"""
    service = object.__new__(DocumentIngestionService)

    calls = []
    persisted_chunks = [object()]
    commit_error = RuntimeError("模拟分块提交失败")

    async def fake_persist(document_id, chunks):
        calls.append("persist")
        return persisted_chunks

    async def fake_commit():
        calls.append("commit")
        raise commit_error

    monkeypatch.setattr(service, "_persist_chunks", fake_persist)
    monkeypatch.setattr(service, "_commit_chunks", fake_commit)

    with pytest.raises(RuntimeError, match="模拟分块提交失败") as exc_info:
        await service._save_document_chunks(123, [object()])

    assert exc_info.value is commit_error
    assert calls == ["persist", "commit"]


@pytest.mark.asyncio
async def test_mark_document_failed_success():
    """测试成功将文档状态更新为 failed。"""
    service = object.__new__(DocumentIngestionService)

    calls = []
    original_error = RuntimeError("模拟分块保存失败")

    class FakeDocumentService:
        async def update_status(
            self,
            document_id,
            status,
            error_message=None,
        ):
            calls.append((document_id, status, error_message))

    service.document_service = FakeDocumentService()

    await service._mark_document_failed(123, original_error)

    assert calls == [
        (123, "failed", "模拟分块保存失败"),
    ]


@pytest.mark.asyncio
async def test_mark_document_failed_uses_fallback_message():
    """测试原始异常没有有效描述时仍生成非空错误信息。"""
    service = object.__new__(DocumentIngestionService)

    calls = []
    original_error = RuntimeError("   ")

    class FakeDocumentService:
        async def update_status(
            self,
            document_id,
            status,
            error_message=None,
        ):
            calls.append((document_id, status, error_message))

    service.document_service = FakeDocumentService()

    await service._mark_document_failed(123, original_error)

    assert len(calls) == 1
    assert calls[0][0] == 123
    assert calls[0][1] == "failed"
    assert calls[0][2]
    assert "RuntimeError" in calls[0][2]


@pytest.mark.asyncio
async def test_mark_document_failed_preserves_original_error():
    """测试状态更新失败时不覆盖最初的分块保存异常。"""
    service = object.__new__(DocumentIngestionService)

    original_error = RuntimeError("原始分块保存异常")

    class FakeDocumentService:
        async def update_status(
            self,
            document_id,
            status,
            error_message=None,
        ):
            raise OSError("模拟文档状态更新失败")

    service.document_service = FakeDocumentService()

    await service._mark_document_failed(123, original_error)

    assert any("文档状态更新失败" in note for note in original_error.__notes__)


@pytest.mark.asyncio
async def test_save_document_chunks_safely_success(monkeypatch):
    """测试分块保存成功时直接返回结果。"""
    service = object.__new__(DocumentIngestionService)

    chunks = [object(), object()]
    persisted_chunks = [object(), object()]
    calls = []

    async def fake_save(document_id, input_chunks):
        calls.append(("save", document_id, input_chunks))
        return persisted_chunks

    async def fake_mark_failed(document_id, original_error):
        calls.append(("mark_failed", document_id, original_error))

    monkeypatch.setattr(service, "_save_document_chunks", fake_save)
    monkeypatch.setattr(service, "_mark_document_failed", fake_mark_failed)

    result = await service._save_document_chunks_safely(123, chunks)

    assert result is persisted_chunks
    assert calls == [("save", 123, chunks)]


@pytest.mark.asyncio
async def test_save_document_chunks_safely_marks_failure(monkeypatch):
    """测试分块保存失败后更新文档失败状态。"""
    service = object.__new__(DocumentIngestionService)

    original_error = RuntimeError("模拟分块保存失败")
    calls = []

    async def fake_save(document_id, chunks):
        calls.append(("save", document_id))
        raise original_error

    async def fake_mark_failed(document_id, error):
        calls.append(("mark_failed", document_id, error))

    monkeypatch.setattr(service, "_save_document_chunks", fake_save)
    monkeypatch.setattr(service, "_mark_document_failed", fake_mark_failed)

    with pytest.raises(RuntimeError, match="模拟分块保存失败") as exc_info:
        await service._save_document_chunks_safely(123, [object()])

    assert exc_info.value is original_error
    assert calls == [
        ("save", 123),
        ("mark_failed", 123, original_error),
    ]


@pytest.mark.asyncio
async def test_save_document_chunks_safely_preserves_error_when_mark_fails(
    monkeypatch,
):
    """测试失败状态更新意外抛出异常时保留原始保存异常。"""
    service = object.__new__(DocumentIngestionService)

    original_error = RuntimeError("原始分块保存异常")
    calls = []

    async def fake_save(document_id, chunks):
        calls.append("save")
        raise original_error

    async def fake_mark_failed(document_id, error):
        calls.append("mark_failed")
        raise OSError("模拟状态更新异常")

    monkeypatch.setattr(service, "_save_document_chunks", fake_save)
    monkeypatch.setattr(service, "_mark_document_failed", fake_mark_failed)

    with pytest.raises(RuntimeError, match="原始分块保存异常") as exc_info:
        await service._save_document_chunks_safely(123, [object()])

    assert exc_info.value is original_error
    assert calls == ["save", "mark_failed"]
    assert any("失败状态更新异常" in note for note in original_error.__notes__)


@pytest.mark.asyncio
async def test_create_document_record_success():
    """测试成功创建文档元数据。"""
    service = object.__new__(DocumentIngestionService)

    stored_file = type(
        "FakeStoredFile",
        (),
        {
            "original_filename": "测试文档.pdf",
            "file_path": "/tmp/test-document.pdf",
            "file_size": 1024,
            "content_hash": "a" * 64,
        },
    )()

    validated_file = type(
        "FakeValidatedFile",
        (),
        {"file_type": "pdf"},
    )()

    expected_document = object()
    calls = []

    class FakeDocumentService:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return expected_document

    class FakeStorage:
        async def delete(self, file_path):
            raise AssertionError("创建成功时不应删除文件")

    service.document_service = FakeDocumentService()
    service.storage = FakeStorage()

    result = await service._create_document_record(
        123,
        stored_file,
        validated_file,
    )

    assert result is expected_document
    assert calls == [
        {
            "knowledge_base_id": 123,
            "name": "测试文档.pdf",
            "file_type": "pdf",
            "file_path": "/tmp/test-document.pdf",
            "file_size": 1024,
            "content_hash": "a" * 64,
        }
    ]


@pytest.mark.asyncio
async def test_create_document_record_cleans_file_on_error():
    """测试创建文档记录失败后清理原始文件。"""
    service = object.__new__(DocumentIngestionService)

    stored_file = type(
        "FakeStoredFile",
        (),
        {
            "original_filename": "测试文档.pdf",
            "file_path": "/tmp/test-document.pdf",
            "file_size": 1024,
            "content_hash": "a" * 64,
        },
    )()

    validated_file = type(
        "FakeValidatedFile",
        (),
        {"file_type": "pdf"},
    )()

    original_error = RuntimeError("模拟文档记录创建失败")
    deleted_paths = []

    class FakeDocumentService:
        async def create(self, **kwargs):
            raise original_error

        async def get_by_content_hash(self, knowledge_base_id, content_hash):
            return None

    class FakeStorage:
        async def delete(self, file_path):
            deleted_paths.append(file_path)

    service.document_service = FakeDocumentService()
    service.storage = FakeStorage()

    with pytest.raises(RuntimeError, match="模拟文档记录创建失败") as exc_info:
        await service._create_document_record(
            123,
            stored_file,
            validated_file,
        )

    assert exc_info.value is original_error
    assert deleted_paths == [stored_file.file_path]


@pytest.mark.asyncio
async def test_create_document_record_preserves_error_when_cleanup_fails():
    """测试文件清理失败时仍保留文档创建异常。"""
    service = object.__new__(DocumentIngestionService)

    stored_file = type(
        "FakeStoredFile",
        (),
        {
            "original_filename": "测试文档.pdf",
            "file_path": "/tmp/test-document.pdf",
            "file_size": 1024,
            "content_hash": "a" * 64,
        },
    )()

    validated_file = type(
        "FakeValidatedFile",
        (),
        {"file_type": "pdf"},
    )()

    original_error = RuntimeError("原始文档创建异常")

    class FakeDocumentService:
        async def create(self, **kwargs):
            raise original_error

        async def get_by_content_hash(self, knowledge_base_id, content_hash):
            return None

    class FakeStorage:
        async def delete(self, file_path):
            raise OSError("模拟文件清理失败")

    service.document_service = FakeDocumentService()
    service.storage = FakeStorage()

    with pytest.raises(RuntimeError, match="原始文档创建异常") as exc_info:
        await service._create_document_record(
            123,
            stored_file,
            validated_file,
        )

    assert exc_info.value is original_error
    assert any("文件清理异常" in note for note in original_error.__notes__)


@pytest.mark.asyncio
async def test_create_document_record_preserves_file_when_database_references_it():
    """测试提交后刷新失败，但数据库已引用文件时保留文件。"""
    service = object.__new__(DocumentIngestionService)

    stored_file = type(
        "FakeStoredFile",
        (),
        {
            "original_filename": "测试文档.pdf",
            "file_path": "/tmp/test-document.pdf",
            "file_size": 1024,
            "content_hash": "a" * 64,
        },
    )()

    validated_file = type(
        "FakeValidatedFile",
        (),
        {"file_type": "pdf"},
    )()

    original_error = RuntimeError("模拟刷新失败")
    deleted_paths = []

    existing_document = type(
        "FakeDocument",
        (),
        {"file_path": stored_file.file_path},
    )()

    class FakeDocumentService:
        async def create(self, **kwargs):
            raise original_error

        async def get_by_content_hash(self, knowledge_base_id, content_hash):
            return existing_document

    class FakeStorage:
        async def delete(self, file_path):
            deleted_paths.append(file_path)

    service.document_service = FakeDocumentService()
    service.storage = FakeStorage()

    with pytest.raises(RuntimeError, match="模拟刷新失败") as exc_info:
        await service._create_document_record(
            123,
            stored_file,
            validated_file,
        )

    assert exc_info.value is original_error
    assert deleted_paths == []
    assert any("已保留原始文件" in note for note in original_error.__notes__)


@pytest.mark.asyncio
async def test_create_document_record_preserves_file_when_lookup_fails():
    """测试无法确认数据库状态时保留文件。"""
    service = object.__new__(DocumentIngestionService)

    stored_file = type(
        "FakeStoredFile",
        (),
        {
            "original_filename": "测试文档.pdf",
            "file_path": "/tmp/test-document.pdf",
            "file_size": 1024,
            "content_hash": "a" * 64,
        },
    )()

    validated_file = type(
        "FakeValidatedFile",
        (),
        {"file_type": "pdf"},
    )()

    original_error = RuntimeError("模拟创建失败")
    deleted_paths = []

    class FakeDocumentService:
        async def create(self, **kwargs):
            raise original_error

        async def get_by_content_hash(self, knowledge_base_id, content_hash):
            raise OSError("模拟数据库查询失败")

    class FakeStorage:
        async def delete(self, file_path):
            deleted_paths.append(file_path)

    service.document_service = FakeDocumentService()
    service.storage = FakeStorage()

    with pytest.raises(RuntimeError, match="模拟创建失败") as exc_info:
        await service._create_document_record(
            123,
            stored_file,
            validated_file,
        )

    assert exc_info.value is original_error
    assert deleted_paths == []
    assert any("已保留原始文件" in note for note in original_error.__notes__)


@pytest.mark.asyncio
async def test_ingest_success_persists_document_and_chunks(database, tmp_path):
    """测试完整导入流程能够持久化文档和分块。"""
    from pathlib import Path

    from app.ingestion.storage import LocalFileStorage
    from app.models import Document

    _, session_factory = database

    async with session_factory() as session:
        knowledge_base = await KnowledgeBaseService(session).create(
            name="导入集成测试知识库",
        )

        storage = LocalFileStorage(
            upload_dir=tmp_path / "uploads",
            max_size_bytes=1024,
        )

        service = DocumentIngestionService(
            session=session,
            chunk_processor=create_chunk_processor(),
            storage=storage,
            validator=UploadFileValidator(max_size_bytes=1024),
        )

        source_content = "第一段内容。\n\n第二段内容。"
        document = await service.ingest(
            knowledge_base_id=knowledge_base.id,
            upload_file=make_upload_file(
                source_content.encode("utf-8"),
                filename="knowledgeflow-test.txt",
            ),
        )

        assert isinstance(document, Document)
        assert document.id is not None
        assert document.knowledge_base_id == knowledge_base.id
        assert document.name == "knowledgeflow-test.txt"
        assert document.file_type == "txt"
        assert document.file_size == len(source_content.encode("utf-8"))
        assert document.status == "completed"
        assert document.error_message is None

        assert Path(document.file_path).is_file()
        assert Path(document.file_path).read_bytes() == source_content.encode("utf-8")

        chunks = await service.chunk_repository.get_by_document(document.id)

        assert len(chunks) >= 1
        assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
        assert all(chunk.content.strip() for chunk in chunks)
        assert all(chunk.token_count is not None for chunk in chunks)

        reconstructed_content = "".join(chunk.content for chunk in chunks)
        assert source_content.replace("\\n\\n", "\\n") in reconstructed_content


@pytest.mark.asyncio
async def test_ingest_parse_failure_deletes_file_and_creates_no_document(
    database,
    tmp_path,
):
    """测试解析失败时清理原始文件且不创建文档记录。"""
    from pathlib import Path

    from app.ingestion.parsers.base import DocumentParseError
    from app.ingestion.storage import LocalFileStorage

    _, session_factory = database

    async with session_factory() as session:
        knowledge_base = await KnowledgeBaseService(session).create(
            name="解析失败集成测试知识库",
        )

        storage = LocalFileStorage(
            upload_dir=tmp_path / "uploads",
            max_size_bytes=1024,
        )

        service = DocumentIngestionService(
            session=session,
            chunk_processor=create_chunk_processor(),
            storage=storage,
            validator=UploadFileValidator(max_size_bytes=1024),
        )

        original_parse = service.parser_registry.get_parser("txt").parse

        async def failing_parse(file_path):
            raise DocumentParseError("模拟 TXT 解析失败")

        service.parser_registry.get_parser("txt").parse = failing_parse

        with pytest.raises(DocumentParseError, match="模拟 TXT 解析失败"):
            await service.ingest(
                knowledge_base_id=knowledge_base.id,
                upload_file=make_upload_file(
                    b"KnowledgeFlow parse failure test",
                    filename="parse-failure.txt",
                ),
            )

        documents = await service.document_service.repository.get_by_knowledge_base(
            knowledge_base.id,
        )

        assert documents == []

        upload_dir = Path(storage.upload_dir)
        assert not list(upload_dir.glob("*"))

        service.parser_registry.get_parser("txt").parse = original_parse


@pytest.mark.asyncio
async def test_ingest_duplicate_file_deletes_new_file_and_preserves_original(
    database,
    tmp_path,
):
    """测试重复导入时清理新文件并保留原文档。"""
    from pathlib import Path

    from app.ingestion.storage import LocalFileStorage

    _, session_factory = database

    async with session_factory() as session:
        knowledge_base = await KnowledgeBaseService(session).create(
            name="重复导入集成测试知识库",
        )

        storage = LocalFileStorage(
            upload_dir=tmp_path / "uploads",
            max_size_bytes=1024,
        )

        service = DocumentIngestionService(
            session=session,
            chunk_processor=create_chunk_processor(),
            storage=storage,
            validator=UploadFileValidator(max_size_bytes=1024),
        )

        source_content = b"KnowledgeFlow duplicate integration test"

        original_document = await service.ingest(
            knowledge_base_id=knowledge_base.id,
            upload_file=make_upload_file(
                source_content,
                filename="original.txt",
            ),
        )

        original_file = Path(original_document.file_path)

        assert original_file.is_file()

        with pytest.raises(DocumentAlreadyExistsError) as exc_info:
            await service.ingest(
                knowledge_base_id=knowledge_base.id,
                upload_file=make_upload_file(
                    source_content,
                    filename="duplicate.txt",
                ),
            )

        assert exc_info.value.document_id == original_document.id

        # 原始文件必须保留，新上传的重复文件必须清理。
        assert original_file.is_file()
        assert original_file.read_bytes() == source_content

        upload_files = list(Path(storage.upload_dir).glob("*"))
        assert upload_files == [original_file]

        # 数据库中只能存在第一次成功导入的文档。
        documents = await service.document_service.get_by_knowledge_base(
            knowledge_base.id,
        )

        assert len(documents) == 1
        assert documents[0].id == original_document.id
        assert documents[0].status == "completed"


@pytest.mark.asyncio
async def test_ingest_chunk_persistence_failure_rolls_back_and_marks_failed(
    database,
    tmp_path,
    monkeypatch,
):
    """测试分块 flush 后发生异常时回滚数据并保留原始文件。"""
    from pathlib import Path

    from app.ingestion.storage import LocalFileStorage

    _, session_factory = database

    async with session_factory() as session:
        knowledge_base = await KnowledgeBaseService(session).create(
            name="分块持久化失败集成测试知识库",
        )
        knowledge_base_id = knowledge_base.id

        storage = LocalFileStorage(
            upload_dir=tmp_path / "uploads",
            max_size_bytes=1024,
        )

        service = DocumentIngestionService(
            session=session,
            chunk_processor=create_chunk_processor(),
            storage=storage,
            validator=UploadFileValidator(max_size_bytes=1024),
        )

        original_create_many = service.chunk_repository.create_many
        original_error = RuntimeError("模拟分块 flush 后保存失败")
        calls = []

        async def failing_create_many(entities):
            # 先执行真实批量写入和 flush，再模拟后续异常。
            persisted = await original_create_many(entities)
            calls.append(len(persisted))
            raise original_error

        monkeypatch.setattr(
            service.chunk_repository,
            "create_many",
            failing_create_many,
        )

        source_content = b"KnowledgeFlow chunk persistence failure integration test"

        with pytest.raises(
            RuntimeError,
            match="模拟分块 flush 后保存失败",
        ) as exc_info:
            await service.ingest(
                knowledge_base_id=knowledge_base_id,
                upload_file=make_upload_file(
                    source_content,
                    filename="chunk-persistence-failure.txt",
                ),
            )

        assert exc_info.value is original_error
        assert calls
        assert calls[0] > 0

        # 文档记录应保留，并且状态更新为 failed。
        documents = await service.document_service.get_by_knowledge_base(
            knowledge_base_id,
        )

        assert len(documents) == 1

        document = documents[0]

        assert document.status == "failed"
        assert document.error_message == str(original_error)

        # 原始上传文件必须保留，供后续重试或排查。
        original_file = Path(document.file_path)

        assert original_file.is_file()
        assert original_file.read_bytes() == source_content

        # flush 后写入的分块必须全部回滚。
        chunks = await service.chunk_repository.get_by_document(document.id)

        assert chunks == []


@pytest.mark.asyncio
async def test_ingest_final_status_update_failure_preserves_chunks(
    database,
    tmp_path,
    monkeypatch,
):
    """测试最终状态更新失败时保留已提交的文档、分块和原始文件。"""
    from pathlib import Path

    from app.ingestion.storage import LocalFileStorage

    _, session_factory = database

    async with session_factory() as session:
        knowledge_base = await KnowledgeBaseService(session).create(
            name="最终状态更新失败测试知识库",
        )

        storage = LocalFileStorage(
            upload_dir=tmp_path / "uploads",
            max_size_bytes=1024,
        )
        service = DocumentIngestionService(
            session=session,
            chunk_processor=create_chunk_processor(),
            storage=storage,
            validator=UploadFileValidator(max_size_bytes=1024),
        )

        original_error = RuntimeError("模拟最终状态更新失败")

        original_update_status = service.document_service.update_status

        async def failing_update_status(**kwargs):
            if kwargs["status"] == "completed":
                raise original_error
            return await original_update_status(**kwargs)

        monkeypatch.setattr(
            service.document_service,
            "update_status",
            failing_update_status,
        )

        source_content = b"KnowledgeFlow final status failure integration test"

        with pytest.raises(RuntimeError, match="模拟最终状态更新失败") as exc_info:
            await service.ingest(
                knowledge_base_id=knowledge_base.id,
                upload_file=make_upload_file(
                    source_content,
                    filename="final-status-failure.txt",
                ),
            )

        assert exc_info.value is original_error

        documents = await service.document_service.get_by_knowledge_base(
            knowledge_base.id,
        )
        assert len(documents) == 1

        document = documents[0]
        assert document.status == "processing"

        chunks = await service.chunk_repository.get_by_document(document.id)
        assert len(chunks) > 0

        original_file = Path(document.file_path)
        assert original_file.is_file()
        assert original_file.read_bytes() == source_content


@pytest.mark.asyncio
async def test_ingest_processing_status_update_failure_preserves_pending_document(
    database,
    tmp_path,
    monkeypatch,
):
    """测试 processing 状态更新失败时保留 pending 文档且不保存分块。"""
    from pathlib import Path

    from app.ingestion.storage import LocalFileStorage

    _, session_factory = database

    async with session_factory() as session:
        knowledge_base = await KnowledgeBaseService(session).create(
            name="processing 状态更新失败测试知识库",
        )

        storage = LocalFileStorage(
            upload_dir=tmp_path / "uploads",
            max_size_bytes=1024,
        )
        service = DocumentIngestionService(
            session=session,
            chunk_processor=create_chunk_processor(),
            storage=storage,
            validator=UploadFileValidator(max_size_bytes=1024),
        )

        original_error = RuntimeError("模拟 processing 状态更新失败")

        original_update_status = service.document_service.update_status

        async def failing_update_status(**kwargs):
            if kwargs["status"] == "processing":
                raise original_error
            return await original_update_status(**kwargs)

        monkeypatch.setattr(
            service.document_service,
            "update_status",
            failing_update_status,
        )

        source_content = b"KnowledgeFlow processing status failure integration test"

        with pytest.raises(
            RuntimeError,
            match="模拟 processing 状态更新失败",
        ) as exc_info:
            await service.ingest(
                knowledge_base_id=knowledge_base.id,
                upload_file=make_upload_file(
                    source_content,
                    filename="processing-status-failure.txt",
                ),
            )

        assert exc_info.value is original_error

        documents = await service.document_service.get_by_knowledge_base(
            knowledge_base.id,
        )
        assert len(documents) == 1

        document = documents[0]
        assert document.status == "pending"

        chunks = await service.chunk_repository.get_by_document(document.id)
        assert chunks == []

        original_file = Path(document.file_path)
        assert original_file.is_file()
        assert original_file.read_bytes() == source_content


@pytest.mark.asyncio
async def test_ingest_indexes_persisted_chunks_before_completion(database, tmp_path, monkeypatch):
    """测试分块持久化后建立向量索引，再完成导入。"""
    from pathlib import Path

    from app.services.vector_index import VectorIndexService

    _, session_factory = database

    async with session_factory() as session:
        kb = await KnowledgeBaseService(session).create(name="向量索引成功集成测试知识库")
        storage = LocalFileStorage(upload_dir=tmp_path / "uploads")
        vector_index = VectorIndexService(object(), object())
        indexed = {}

        async def fake_index_chunks(chunks, knowledge_base_id):
            indexed["chunks"] = chunks
            indexed["knowledge_base_id"] = knowledge_base_id

        monkeypatch.setattr(vector_index, "index_chunks", fake_index_chunks)

        service = DocumentIngestionService(
            session=session,
            chunk_processor=create_chunk_processor(),
            storage=storage,
            validator=UploadFileValidator(max_size_bytes=1024),
            vector_index_service=vector_index,
        )

        document = await service.ingest(
            knowledge_base_id=kb.id,
            upload_file=make_upload_file(
                b"KnowledgeFlow vector indexing integration test",
                filename="vector-index-success.txt",
            ),
        )

        persisted = await service.chunk_repository.get_by_document(document.id)

        assert document.status == "completed"
        assert indexed["knowledge_base_id"] == kb.id
        assert [c.id for c in indexed["chunks"]] == [c.id for c in persisted]
        assert all(c.id is not None for c in indexed["chunks"])
        assert Path(document.file_path).is_file()


@pytest.mark.asyncio
async def test_ingest_vector_index_failure_preserves_chunks_and_file(
    database, tmp_path, monkeypatch
):
    """测试向量索引失败时保留 SQLite 分块和原始文件。"""
    from pathlib import Path

    from app.services.vector_index import VectorIndexService

    _, session_factory = database

    async with session_factory() as session:
        kb = await KnowledgeBaseService(session).create(name="向量索引失败集成测试知识库")
        storage = LocalFileStorage(upload_dir=tmp_path / "uploads")
        vector_index = VectorIndexService(object(), object())
        original_error = RuntimeError("模拟 ChromaDB 写入失败")

        async def failing_index_chunks(chunks, knowledge_base_id):
            raise original_error

        monkeypatch.setattr(vector_index, "index_chunks", failing_index_chunks)

        service = DocumentIngestionService(
            session=session,
            chunk_processor=create_chunk_processor(),
            storage=storage,
            validator=UploadFileValidator(max_size_bytes=1024),
            vector_index_service=vector_index,
        )

        source = b"KnowledgeFlow vector indexing failure integration test"

        with pytest.raises(RuntimeError, match="模拟 ChromaDB 写入失败") as exc:
            await service.ingest(
                knowledge_base_id=kb.id,
                upload_file=make_upload_file(source, filename="vector-index-failure.txt"),
            )

        assert exc.value is original_error
        documents = await service.document_service.get_by_knowledge_base(kb.id)
        assert len(documents) == 1

        document = documents[0]
        assert document.status == "failed"

        chunks = await service.chunk_repository.get_by_document(document.id)
        assert chunks
        assert all(chunk.id is not None for chunk in chunks)

        original_file = Path(document.file_path)
        assert original_file.is_file()
        assert original_file.read_bytes() == source


def test_chunk_document_enables_markdown_heading_extraction():
    """Markdown 文档应启用标题上下文提取。"""
    from app.ingestion.chunker import TextChunk
    from app.ingestion.parsers.base import ParsedDocument

    content = "# 项目标题\n正文内容"
    start = content.index("正文内容")

    chunks = [
        TextChunk(
            chunk_index=0,
            content="正文内容",
            start_index=start,
            end_index=len(content),
            token_count=4,
            metadata={"heading_path": ["项目标题"]},
        )
    ]

    class FakeChunkProcessor:
        def process(self, text, markdown=False):
            assert text == content
            assert markdown is True
            return chunks

    service = object.__new__(DocumentIngestionService)
    service.chunk_processor = FakeChunkProcessor()

    document = ParsedDocument(
        content=content,
        file_type="md",
    )

    result = service._chunk_document(document)

    assert result == chunks
    assert result[0].metadata["heading_path"] == ["项目标题"]


@pytest.mark.asyncio
async def test_ingest_rejects_deleting_knowledge_base_without_storing_file(
    database,
    tmp_path,
):
    """删除中的知识库不允许导入文档，且不得保存上传文件。"""
    _, session_factory = database

    async with session_factory() as session:
        kb = await KnowledgeBaseService(session).create(name="删除状态导入保护测试知识库")
        kb.status = "deleting"
        await session.commit()

        storage = LocalFileStorage(upload_dir=tmp_path / "uploads")
        service = DocumentIngestionService(
            session=session,
            chunk_processor=create_chunk_processor(),
            storage=storage,
        )

        with pytest.raises(
            KnowledgeBaseDeletingError,
            match=f"知识库正在删除，无法导入文档：{kb.id}",
        ):
            await service.ingest(
                knowledge_base_id=kb.id,
                upload_file=make_upload_file(b"must not be stored"),
            )

        assert not (tmp_path / "uploads").exists()


@pytest.mark.asyncio
async def test_ingest_rejects_missing_knowledge_base_without_storing_file(
    database,
    tmp_path,
):
    """不存在的知识库不允许导入文档，且不得保存上传文件。"""
    _, session_factory = database

    async with session_factory() as session:
        storage = LocalFileStorage(upload_dir=tmp_path / "uploads")
        service = DocumentIngestionService(
            session=session,
            chunk_processor=create_chunk_processor(),
            storage=storage,
        )

        with pytest.raises(
            KnowledgeBaseNotFoundError,
            match="知识库不存在：999",
        ):
            await service.ingest(
                knowledge_base_id=999,
                upload_file=make_upload_file(b"must not be stored"),
            )

        assert not (tmp_path / "uploads").exists()
