"""KnowledgeFlow PDF 文档解析器测试。"""

import asyncio

import pytest
from pypdf import PdfWriter
from pypdf._page import PageObject

from app.ingestion.parsers.base import (
    BaseParser,
    DocumentParseError,
    ParsedDocument,
    UnsupportedFileTypeError,
)
from app.ingestion.parsers.pdf import PDFParser


@pytest.fixture
def parser():
    """创建 PDF 解析器。"""
    return PDFParser()


def create_pdf(file_path, page_count=1, password=None):
    """创建用于测试的 PDF 文件。"""
    writer = PdfWriter()

    for _ in range(page_count):
        writer.add_blank_page(width=595, height=842)

    if password:
        writer.encrypt(password)

    with file_path.open("wb") as file:
        writer.write(file)


def create_text_pdf(file_path, texts):
    """生成包含真实文本内容的最小 PDF 测试文件。"""
    objects = [
        b"",
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    page_ids = []

    for text in texts:
        # 使用 PDF 字面字符串格式，测试文本限定为 ASCII。
        escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

        stream = (f"BT\n/F1 12 Tf\n72 720 Td\n({escaped_text}) Tj\nET\n").encode("ascii")

        page_id = len(objects)
        content_id = page_id + 1
        page_ids.append(page_id)

        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("ascii")
        )

        objects.append(
            b"<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"endstream"
        )

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)

    objects[2] = (f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>").encode("ascii")

    # 写入 PDF 对象并记录每个对象的字节偏移。
    pdf_data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]

    for object_id, obj in enumerate(objects[1:], start=1):
        offsets.append(len(pdf_data))
        pdf_data.extend(f"{object_id} 0 obj\n".encode("ascii"))
        pdf_data.extend(obj)
        pdf_data.extend(b"\nendobj\n")

    # 写入交叉引用表。
    xref_offset = len(pdf_data)
    pdf_data.extend(f"xref\n0 {len(objects)}\n".encode("ascii"))
    pdf_data.extend(b"0000000000 65535 f \n")

    for offset in offsets[1:]:
        pdf_data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf_data.extend(
        (
            f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )

    file_path.write_bytes(pdf_data)


@pytest.mark.asyncio
async def test_pdf_parser_implements_base_parser(parser):
    """测试 PDF 解析器实现统一基础接口。"""
    assert isinstance(parser, BaseParser)


@pytest.mark.asyncio
async def test_pdf_parser_extracts_multiple_pages(parser, tmp_path, monkeypatch):
    """测试提取多页 PDF 文本并保留页码。"""
    file_path = tmp_path / "document.pdf"
    create_pdf(file_path, page_count=2)

    page_texts = iter(["第一页内容", "第二页内容"])

    def fake_extract_text(self, *args, **kwargs):
        return next(page_texts)

    monkeypatch.setattr(PageObject, "extract_text", fake_extract_text)

    result = await parser.parse(file_path)

    assert isinstance(result, ParsedDocument)
    assert result.file_type == "pdf"
    assert result.content == "第一页内容\n第二页内容"
    assert result.metadata["page_count"] == 2
    assert result.metadata["char_count"] == len(result.content)
    assert result.metadata["pages"] == [
        {
            "page_number": 1,
            "content": "第一页内容",
            "char_count": 5,
        },
        {
            "page_number": 2,
            "content": "第二页内容",
            "char_count": 5,
        },
    ]
    assert result.warnings == ()


@pytest.mark.asyncio
async def test_pdf_parser_warns_about_empty_page(parser, tmp_path, monkeypatch):
    """测试空白页面产生警告，但不影响其他页面。"""
    file_path = tmp_path / "empty_page.pdf"
    create_pdf(file_path, page_count=2)

    page_texts = iter(["第一页内容", ""])

    def fake_extract_text(self, *args, **kwargs):
        return next(page_texts)

    monkeypatch.setattr(PageObject, "extract_text", fake_extract_text)

    result = await parser.parse(file_path)

    assert result.content == "第一页内容\n"
    assert result.metadata["page_count"] == 2
    assert len(result.warnings) == 1
    assert "第 2 页" in result.warnings[0]


@pytest.mark.asyncio
async def test_pdf_parser_warns_when_no_text_can_be_extracted(parser, tmp_path, monkeypatch):
    """测试整份 PDF 没有可提取文本时产生 OCR 提示。"""
    file_path = tmp_path / "scanned.pdf"
    create_pdf(file_path, page_count=1)

    monkeypatch.setattr(PageObject, "extract_text", lambda self, *a, **k: "")

    result = await parser.parse(file_path)

    assert result.content == ""
    assert result.metadata["page_count"] == 1
    assert any("OCR" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_pdf_parser_handles_page_extraction_error(parser, tmp_path, monkeypatch):
    """测试单页文本提取异常不会导致整个解析失败。"""
    file_path = tmp_path / "page_error.pdf"
    create_pdf(file_path, page_count=2)

    page_texts = iter(["第一页内容", RuntimeError("模拟页面提取异常")])

    def fake_extract_text(self, *args, **kwargs):
        value = next(page_texts)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(PageObject, "extract_text", fake_extract_text)

    result = await parser.parse(file_path)

    assert result.metadata["page_count"] == 2
    assert result.metadata["pages"][0]["content"] == "第一页内容"
    assert result.metadata["pages"][1]["content"] == ""
    assert any("第 2 页" in warning for warning in result.warnings)
    assert any("第 2 页文本提取失败" in warning for warning in result.warnings)
    assert not any("第 2 页未提取到文本" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_pdf_parser_supports_uppercase_extension(parser, tmp_path):
    """测试支持大写 PDF 扩展名。"""
    file_path = tmp_path / "document.PDF"
    create_pdf(file_path)

    result = await parser.parse(file_path)

    assert result.file_type == "pdf"
    assert result.metadata["page_count"] == 1


@pytest.mark.asyncio
async def test_pdf_parser_rejects_unsupported_extension(parser, tmp_path):
    """测试拒绝不支持的文件扩展名。"""
    file_path = tmp_path / "document.txt"
    file_path.write_text("测试内容", encoding="utf-8")

    with pytest.raises(UnsupportedFileTypeError):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_pdf_parser_rejects_missing_file(parser, tmp_path):
    """测试文件不存在时抛出解析异常。"""
    file_path = tmp_path / "missing.pdf"

    with pytest.raises(DocumentParseError, match="不存在"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_pdf_parser_rejects_directory(parser, tmp_path):
    """测试拒绝将目录作为 PDF 文件解析。"""
    directory = tmp_path / "document.pdf"
    directory.mkdir()

    with pytest.raises(DocumentParseError, match="普通文件"):
        await parser.parse(directory)


@pytest.mark.asyncio
async def test_pdf_parser_rejects_empty_file(parser, tmp_path):
    """测试拒绝零字节 PDF 文件。"""
    file_path = tmp_path / "empty.pdf"
    file_path.write_bytes(b"")

    with pytest.raises(DocumentParseError, match="损坏"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_pdf_parser_rejects_corrupted_file(parser, tmp_path):
    """测试拒绝损坏的 PDF 文件。"""
    file_path = tmp_path / "corrupted.pdf"
    file_path.write_bytes(b"This is not a valid PDF file")

    with pytest.raises(DocumentParseError, match="损坏"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_pdf_parser_rejects_encrypted_file(parser, tmp_path):
    """测试拒绝加密 PDF 文件。"""
    file_path = tmp_path / "encrypted.pdf"
    create_pdf(file_path, password="secret")

    with pytest.raises(DocumentParseError, match="加密"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_pdf_parser_wraps_read_error(parser, tmp_path, monkeypatch):
    """测试将文件读取异常转换为统一解析异常。"""
    file_path = tmp_path / "document.pdf"
    create_pdf(file_path)

    def raise_read_error(*args, **kwargs):
        raise OSError("模拟磁盘读取失败")

    monkeypatch.setattr(type(file_path), "open", raise_read_error)

    with pytest.raises(DocumentParseError, match="读取失败"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_pdf_parser_uses_thread_for_file_reading(parser, tmp_path, monkeypatch):
    """测试 PDF 文件读取通过线程池执行。"""
    file_path = tmp_path / "document.pdf"
    create_pdf(file_path)

    original_to_thread = asyncio.to_thread
    called = False

    async def track_to_thread(func, *args, **kwargs):
        nonlocal called
        called = True
        return await original_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", track_to_thread)

    result = await parser.parse(file_path)

    assert called is True
    assert result.metadata["page_count"] == 1


@pytest.mark.asyncio
async def test_pdf_parser_extracts_real_pdf_text(parser, tmp_path):
    """测试使用真实 PDF 文件提取多页文本，不 mock 提取方法。"""
    file_path = tmp_path / "real_text.pdf"

    expected_texts = [
        "KnowledgeFlow PDF integration test",
        "Second page contains another sentence",
    ]

    create_text_pdf(file_path, expected_texts)

    result = await parser.parse(file_path)

    assert result.metadata["page_count"] == 2
    assert len(result.metadata["pages"]) == 2

    extracted_pages = [page["content"].strip() for page in result.metadata["pages"]]

    assert extracted_pages == expected_texts

    assert result.content == "\n".join(page["content"] for page in result.metadata["pages"])

    assert result.metadata["char_count"] == len(result.content)
    assert result.warnings == ()


@pytest.mark.asyncio
async def test_pdf_parser_warns_when_document_has_no_pages(parser, tmp_path):
    """测试没有页面的 PDF 文档产生警告。"""
    file_path = tmp_path / "no_pages.pdf"
    create_pdf(file_path, page_count=0)

    result = await parser.parse(file_path)

    assert result.content == ""
    assert result.metadata["page_count"] == 0
    assert result.metadata["pages"] == []
    assert any("PDF 文档没有页面" in warning for warning in result.warnings)


def make_limited_parser(
    max_pages=500,
    max_page_chars=200_000,
    max_total_chars=2_000_000,
):
    """创建具有指定资源限制的 PDF 解析器。"""
    from app.core.config import Settings

    settings = Settings(
        pdf_max_pages=max_pages,
        pdf_max_page_chars=max_page_chars,
        pdf_max_total_chars=max_total_chars,
        _env_file=None,
    )
    return PDFParser(settings=settings)


@pytest.mark.asyncio
async def test_pdf_parser_rejects_excessive_page_count(tmp_path):
    """测试页面数量超过限制时拒绝解析。"""
    file_path = tmp_path / "too_many_pages.pdf"
    create_pdf(file_path, page_count=3)

    parser = make_limited_parser(max_pages=2)

    with pytest.raises(DocumentParseError, match="页面数量超过限制"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_pdf_parser_rejects_excessive_single_page_text(
    tmp_path,
    monkeypatch,
):
    """测试单页文本超过限制时拒绝解析。"""
    file_path = tmp_path / "long_page.pdf"
    create_pdf(file_path)

    monkeypatch.setattr(
        PageObject,
        "extract_text",
        lambda self, *args, **kwargs: "A" * 11,
    )

    parser = make_limited_parser(max_page_chars=10)

    with pytest.raises(DocumentParseError, match="单页|第 1 页文本长度超过限制"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_pdf_parser_rejects_excessive_total_text(
    tmp_path,
    monkeypatch,
):
    """测试多页累计文本超过限制时拒绝解析。"""
    file_path = tmp_path / "long_document.pdf"
    create_pdf(file_path, page_count=3)

    page_texts = iter(["AAAA", "BBBB", "CCCC"])

    monkeypatch.setattr(
        PageObject,
        "extract_text",
        lambda self, *args, **kwargs: next(page_texts),
    )

    parser = make_limited_parser(
        max_page_chars=9,
        max_total_chars=9,
    )

    with pytest.raises(DocumentParseError, match="全文文本长度超过限制"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_pdf_parser_accepts_text_at_exact_limits(
    tmp_path,
    monkeypatch,
):
    """测试文本长度刚好达到限制时允许解析。"""
    file_path = tmp_path / "exact_limit.pdf"
    create_pdf(file_path, page_count=2)

    page_texts = iter(["AAAA", "BBBB"])

    monkeypatch.setattr(
        PageObject,
        "extract_text",
        lambda self, *args, **kwargs: next(page_texts),
    )

    parser = make_limited_parser(
        max_pages=2,
        max_page_chars=4,
        max_total_chars=9,
    )

    result = await parser.parse(file_path)

    assert result.content == "AAAA\nBBBB"
    assert result.metadata["char_count"] == 9


@pytest.mark.asyncio
async def test_pdf_parser_stops_extracting_after_total_limit_exceeded(
    tmp_path,
    monkeypatch,
):
    """测试全文超限后不再提取后续页面。"""
    file_path = tmp_path / "early_stop.pdf"
    create_pdf(file_path, page_count=3)

    extracted_pages = []

    def fake_extract_text(self, *args, **kwargs):
        extracted_pages.append(self)
        return "AAAA"

    monkeypatch.setattr(PageObject, "extract_text", fake_extract_text)

    parser = make_limited_parser(
        max_page_chars=8,
        max_total_chars=8,
    )

    with pytest.raises(DocumentParseError, match="全文文本长度超过限制"):
        await parser.parse(file_path)

    assert len(extracted_pages) == 2
