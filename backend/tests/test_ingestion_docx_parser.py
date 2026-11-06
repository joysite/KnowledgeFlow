"""DOCX 文档解析器测试。"""

from pathlib import Path

import pytest
from docx import Document as WordDocument

from app.ingestion.parsers.base import (
    BaseParser,
    DocumentParseError,
    UnsupportedFileTypeError,
)
from app.ingestion.parsers.docx import DOCXParser


@pytest.fixture
def parser() -> DOCXParser:
    """创建 DOCX 解析器实例。"""
    return DOCXParser()


def create_docx(file_path: Path) -> Path:
    """创建包含段落和表格的 DOCX 测试文件。"""
    document = WordDocument()

    document.add_heading("KnowledgeFlow 测试文档", level=1)
    document.add_paragraph("这是第一段正文。")
    document.add_paragraph("这是第二段正文。")

    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "名称"
    table.cell(0, 1).text = "版本"
    table.cell(1, 0).text = "KnowledgeFlow"
    table.cell(1, 1).text = "1.0"

    document.add_paragraph("这是表格之后的正文。")

    document.save(file_path)

    return file_path


@pytest.mark.asyncio
async def test_docx_parser_inherits_base_parser(parser):
    """验证 DOCX 解析器实现统一解析器接口。"""
    assert isinstance(parser, BaseParser)


@pytest.mark.asyncio
async def test_docx_parser_extracts_paragraphs_and_tables(parser, tmp_path):
    """验证正文段落、表格内容和文档顺序。"""
    file_path = create_docx(tmp_path / "sample.docx")

    result = await parser.parse(file_path)

    assert result.file_type == "docx"
    assert "KnowledgeFlow 测试文档" in result.content
    assert "这是第一段正文。" in result.content
    assert "这是第二段正文。" in result.content
    assert "名称\t版本" in result.content
    assert "KnowledgeFlow\t1.0" in result.content
    assert "这是表格之后的正文。" in result.content

    assert (
        result.content.index("这是第二段正文。")
        < result.content.index("名称\t版本")
        < result.content.index("这是表格之后的正文。")
    )


@pytest.mark.asyncio
async def test_docx_parser_metadata(parser, tmp_path):
    """验证解析结果元数据。"""
    file_path = create_docx(tmp_path / "metadata.docx")

    result = await parser.parse(file_path)

    assert result.metadata["paragraph_count"] == 4
    assert result.metadata["table_count"] == 1
    assert result.metadata["char_count"] == len(result.content)
    assert result.warnings == ()


@pytest.mark.asyncio
async def test_docx_parser_supports_uppercase_extension(parser, tmp_path):
    """验证大写 DOCX 扩展名。"""
    file_path = create_docx(tmp_path / "sample.DOCX")

    result = await parser.parse(file_path)

    assert result.file_type == "docx"
    assert "KnowledgeFlow 测试文档" in result.content


@pytest.mark.asyncio
async def test_docx_parser_rejects_unsupported_extension(parser, tmp_path):
    """验证不支持的文件扩展名。"""
    file_path = tmp_path / "sample.txt"
    file_path.write_text("测试内容", encoding="utf-8")

    with pytest.raises(UnsupportedFileTypeError):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_docx_parser_rejects_missing_file(parser, tmp_path):
    """验证文件不存在时的异常处理。"""
    file_path = tmp_path / "missing.docx"

    with pytest.raises(DocumentParseError, match="不存在"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_docx_parser_rejects_corrupted_file(parser, tmp_path):
    """验证损坏的 DOCX 文件。"""
    file_path = tmp_path / "corrupted.docx"
    file_path.write_bytes(b"this is not a valid docx file")

    with pytest.raises(DocumentParseError, match="损坏或读取失败"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_docx_parser_empty_document_warning(parser, tmp_path):
    """验证空白 DOCX 文档的警告。"""
    file_path = tmp_path / "empty.docx"
    WordDocument().save(file_path)

    result = await parser.parse(file_path)

    assert result.content == ""
    assert result.metadata["paragraph_count"] == 0
    assert result.metadata["table_count"] == 0
    assert result.metadata["char_count"] == 0
    assert "没有提取到可用文本" in result.warnings[0]


@pytest.mark.asyncio
async def test_docx_parser_empty_paragraphs(parser, tmp_path):
    """验证空段落不会产生多余正文内容。"""
    file_path = tmp_path / "blank_paragraphs.docx"

    document = WordDocument()
    document.add_paragraph("")
    document.add_paragraph("有效内容")
    document.add_paragraph("")
    document.save(file_path)

    result = await parser.parse(file_path)

    assert result.content == "有效内容"
    assert result.metadata["paragraph_count"] == 3
    assert result.warnings == ()


@pytest.mark.asyncio
async def test_docx_parser_table_only_document(parser, tmp_path):
    """验证只有表格、没有正文段落的文档。"""
    file_path = tmp_path / "table_only.docx"

    document = WordDocument()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "字段"
    table.cell(0, 1).text = "值"
    document.save(file_path)

    result = await parser.parse(file_path)

    assert result.content == "字段\t值"
    assert result.metadata["table_count"] == 1
    assert result.warnings == ()


@pytest.mark.asyncio
async def test_docx_parser_uses_worker_thread(parser, tmp_path, monkeypatch):
    """验证文件读取通过 asyncio.to_thread 执行。"""
    file_path = create_docx(tmp_path / "thread.docx")

    import app.ingestion.parsers.docx as docx_module

    original_to_thread = docx_module.asyncio.to_thread
    called = False

    async def tracked_to_thread(function, *args, **kwargs):
        nonlocal called
        called = True
        return await original_to_thread(function, *args, **kwargs)

    monkeypatch.setattr(docx_module.asyncio, "to_thread", tracked_to_thread)

    await parser.parse(file_path)

    assert called
