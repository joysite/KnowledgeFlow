"""KnowledgeFlow 上传文件校验模块测试。"""

import zipfile

import pytest

from app.ingestion.validators import (
    FileValidationError,
    UploadFileValidator,
    ValidatedFile,
)


@pytest.fixture
def validator():
    """创建默认文件校验器。"""
    return UploadFileValidator(max_size_bytes=1024 * 1024)


def create_docx(path):
    """创建具有必要内部结构的最小 DOCX 测试文件。"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", "<document></document>")
    return path


def test_validator_initialization():
    """测试校验器初始化。"""
    assert UploadFileValidator(1024).max_size_bytes == 1024


@pytest.mark.parametrize("size", [0, -1, True, 1.5, "1024"])
def test_validator_rejects_invalid_max_size(size):
    """测试拒绝非法文件大小配置。"""
    with pytest.raises(ValueError):
        UploadFileValidator(size)


@pytest.mark.parametrize(
    "filename",
    [
        "",
        " ",
        ".",
        "..",
        "../test.txt",
        "/tmp/test.txt",
        r"..\test.txt",
        "test\x00.txt",
        "test\n.txt",
    ],
)
def test_validator_rejects_invalid_filename(validator, tmp_path, filename):
    """测试拒绝非法文件名。"""
    path = tmp_path / "test.txt"
    path.write_text("hello", encoding="utf-8")

    with pytest.raises(FileValidationError):
        validator.validate(filename, path)


@pytest.mark.parametrize(
    "filename",
    [
        "test.exe",
        "test",
        "test.pdf.exe",
        "test.html",
    ],
)
def test_validator_rejects_unsupported_extension(
    validator,
    tmp_path,
    filename,
):
    """测试拒绝不支持的文件扩展名。"""
    path = tmp_path / "test.bin"
    path.write_bytes(b"test")

    with pytest.raises(FileValidationError, match="不支持的文件类型"):
        validator.validate(filename, path)


def test_validator_rejects_missing_file(validator, tmp_path):
    """测试拒绝不存在的文件。"""
    with pytest.raises(FileValidationError, match="不存在"):
        validator.validate("test.txt", tmp_path / "missing.txt")


def test_validator_rejects_empty_file(validator, tmp_path):
    """测试拒绝空文件。"""
    path = tmp_path / "empty.txt"
    path.write_bytes(b"")

    with pytest.raises(FileValidationError, match="空文件"):
        validator.validate("empty.txt", path)


def test_validator_rejects_oversized_file(tmp_path):
    """测试拒绝超过大小限制的文件。"""
    validator = UploadFileValidator(max_size_bytes=4)
    path = tmp_path / "large.txt"
    path.write_bytes(b"12345")

    with pytest.raises(FileValidationError, match="超过限制"):
        validator.validate("large.txt", path)


def test_validator_rejects_mismatched_mime_type(validator, tmp_path):
    """测试拒绝与扩展名不匹配的 MIME 类型。"""
    path = tmp_path / "test.txt"
    path.write_text("hello", encoding="utf-8")

    with pytest.raises(FileValidationError, match="MIME 类型"):
        validator.validate(
            "test.txt",
            path,
            "application/pdf",
        )


def test_validator_accepts_generic_mime_type(validator, tmp_path):
    """测试允许浏览器提供通用 MIME 类型。"""
    path = tmp_path / "test.txt"
    path.write_text("hello", encoding="utf-8")

    result = validator.validate(
        "test.txt",
        path,
        "application/octet-stream",
    )

    assert result.content_type == "application/octet-stream"


def test_validator_accepts_pdf(validator, tmp_path):
    """测试有效 PDF 文件。"""
    path = tmp_path / "test.pdf"
    path.write_bytes(b"%PDF-1.7\nminimal test")

    result = validator.validate(
        "test.pdf",
        path,
        "application/pdf",
    )

    assert result == ValidatedFile(
        filename="test.pdf",
        file_type="pdf",
        file_size=21,
        content_type="application/pdf",
    )


def test_validator_rejects_invalid_pdf_signature(validator, tmp_path):
    """测试拒绝伪装成 PDF 的普通文本文件。"""
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"this is not a pdf")

    with pytest.raises(FileValidationError, match="不是有效的 PDF"):
        validator.validate("fake.pdf", path)


def test_validator_accepts_pdf_header_with_leading_bytes(validator, tmp_path):
    """测试允许 PDF 规范允许的前导内容。"""
    path = tmp_path / "test.pdf"
    path.write_bytes(b"\n" * 10 + b"%PDF-1.7\ncontent")

    result = validator.validate("test.pdf", path)

    assert result.file_type == "pdf"


def test_validator_accepts_docx(validator, tmp_path):
    """测试有效 DOCX 文件。"""
    path = create_docx(tmp_path / "test.docx")

    result = validator.validate(
        "test.docx",
        path,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert result.file_type == "docx"
    assert result.file_size == path.stat().st_size


def test_validator_rejects_non_zip_docx(validator, tmp_path):
    """测试拒绝非 ZIP 格式的 DOCX 文件。"""
    path = tmp_path / "fake.docx"
    path.write_bytes(b"not a docx")

    with pytest.raises(FileValidationError, match="ZIP 容器"):
        validator.validate("fake.docx", path)


def test_validator_rejects_incomplete_docx(validator, tmp_path):
    """测试拒绝缺少必要内部文件的 DOCX。"""
    path = tmp_path / "incomplete.docx"

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", "<document></document>")

    with pytest.raises(FileValidationError, match="缺少必要"):
        validator.validate("incomplete.docx", path)


def test_validator_accepts_utf8_txt(validator, tmp_path):
    """测试 UTF-8 TXT 文件。"""
    path = tmp_path / "test.txt"
    path.write_text("这是一个中文测试文件。", encoding="utf-8")

    result = validator.validate("test.txt", path, "text/plain")

    assert result.file_type == "txt"
    assert result.filename == "test.txt"


def test_validator_accepts_utf8_bom_markdown(validator, tmp_path):
    """测试带 UTF-8 BOM 的 Markdown 文件。"""
    path = tmp_path / "test.md"
    path.write_text("# KnowledgeFlow", encoding="utf-8-sig")

    result = validator.validate("test.md", path, "text/markdown")

    assert result.file_type == "md"


def test_validator_rejects_invalid_utf8(validator, tmp_path):
    """测试拒绝非法 UTF-8 编码。"""
    path = tmp_path / "invalid.txt"
    path.write_bytes(b"\xff\xfe\xfa")

    with pytest.raises(FileValidationError, match="UTF-8"):
        validator.validate("invalid.txt", path)


def test_validator_rejects_null_bytes(validator, tmp_path):
    """测试拒绝包含 NUL 字节的文本文件。"""
    path = tmp_path / "invalid.txt"
    path.write_bytes(b"hello\x00world")

    with pytest.raises(FileValidationError, match="NUL"):
        validator.validate("invalid.txt", path)


def test_validator_accepts_markdown_with_generic_mime(validator, tmp_path):
    """测试 Markdown 文件使用通用 MIME 类型。"""
    path = tmp_path / "test.md"
    path.write_text("# KnowledgeFlow", encoding="utf-8")

    result = validator.validate(
        "test.md",
        path,
        "application/octet-stream",
    )

    assert result.file_type == "md"


def test_validator_normalizes_filename(validator, tmp_path):
    """测试文件名首尾空格标准化。"""
    path = tmp_path / "test.txt"
    path.write_text("hello", encoding="utf-8")

    result = validator.validate(" test.txt ", path)

    assert result.filename == "test.txt"


def test_validator_rejects_directory_as_file(validator, tmp_path):
    """测试拒绝目录路径。"""
    with pytest.raises(FileValidationError, match="普通文件"):
        validator.validate("test.txt", tmp_path)


def create_docx_with_content(path, document_content=b"hello", extra_entries=()):
    """创建用于 ZIP 安全测试的 DOCX 文件。"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", b"x")
        archive.writestr("word/document.xml", document_content)
        for name, content in extra_entries:
            archive.writestr(name, content)


def test_docx_rejects_too_many_entries(validator, tmp_path):
    path = tmp_path / "too_many.docx"
    validator.DOCX_MAX_ENTRIES = 2
    create_docx_with_content(path, extra_entries=(("extra.xml", b"x"),))

    with pytest.raises(FileValidationError, match="条目数量"):
        validator._validate_docx(path)


def test_docx_rejects_duplicate_entry_names(validator, tmp_path):
    path = tmp_path / "duplicate.docx"

    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", b"x")
            archive.writestr("word/document.xml", b"x")
            archive.writestr("custom.xml", b"first")
            archive.writestr("custom.xml", b"second")

    with pytest.raises(FileValidationError, match="重复"):
        validator._validate_docx(path)


def test_docx_rejects_excessive_total_uncompressed_size(validator, tmp_path):
    path = tmp_path / "large_total.docx"
    validator.DOCX_MAX_TOTAL_UNCOMPRESSED_SIZE = 5
    validator.DOCX_MAX_SINGLE_FILE_SIZE = 100

    create_docx_with_content(path, document_content=b"12345")

    with pytest.raises(FileValidationError, match="总解压大小"):
        validator._validate_docx(path)


def test_docx_rejects_excessive_single_file_size(validator, tmp_path):
    path = tmp_path / "large_entry.docx"
    validator.DOCX_MAX_SINGLE_FILE_SIZE = 4

    create_docx_with_content(path, document_content=b"12345")

    with pytest.raises(FileValidationError, match="单个文件解压大小"):
        validator._validate_docx(path)


def test_docx_rejects_excessive_compression_ratio(validator, tmp_path):
    path = tmp_path / "high_ratio.docx"
    validator.DOCX_MAX_COMPRESSION_RATIO = 2

    create_docx_with_content(path, document_content=b"A" * 100_000)

    with pytest.raises(FileValidationError, match="压缩比"):
        validator._validate_docx(path)


def test_docx_stream_rejects_excessive_actual_single_file_size(validator, tmp_path):
    path = tmp_path / "stream_single.docx"
    create_docx_with_content(path, document_content=b"A" * 100)
    validator.DOCX_MAX_SINGLE_FILE_SIZE = 50

    with zipfile.ZipFile(path, "r") as archive:
        with pytest.raises(FileValidationError, match="实际解压大小"):
            validator._validate_docx_stream(archive, archive.infolist())


def test_docx_stream_rejects_excessive_actual_total_size(validator, tmp_path):
    path = tmp_path / "stream_total.docx"
    create_docx_with_content(path, document_content=b"A" * 100)
    validator.DOCX_MAX_TOTAL_UNCOMPRESSED_SIZE = 50
    validator.DOCX_MAX_SINGLE_FILE_SIZE = 1024

    with zipfile.ZipFile(path, "r") as archive:
        with pytest.raises(FileValidationError, match="实际总解压大小"):
            validator._validate_docx_stream(archive, archive.infolist())


def test_validate_docx_invokes_stream_validation(validator, tmp_path, monkeypatch):
    path = tmp_path / "stream_integration.docx"
    create_docx_with_content(path)

    original = validator._validate_docx_stream
    called = []

    def tracked_stream_validation(archive, infos):
        called.append(len(infos))
        original(archive, infos)

    monkeypatch.setattr(
        validator,
        "_validate_docx_stream",
        tracked_stream_validation,
    )

    validator._validate_docx(path)

    assert called == [2]
