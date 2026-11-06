"""KnowledgeFlow Markdown 文档解析器测试。"""

import asyncio

import pytest

from app.ingestion.parsers.base import (
    BaseParser,
    DocumentParseError,
    ParsedDocument,
    UnsupportedFileTypeError,
)
from app.ingestion.parsers.markdown import MarkdownParser


@pytest.fixture
def parser():
    """创建 Markdown 解析器。"""
    return MarkdownParser()


@pytest.mark.asyncio
async def test_markdown_parser_implements_base_parser(parser):
    """测试 Markdown 解析器实现统一基础接口。"""
    assert isinstance(parser, BaseParser)


@pytest.mark.asyncio
async def test_markdown_parser_reads_normal_file(parser, tmp_path):
    """测试正常解析 Markdown 文档。"""
    content = "# KnowledgeFlow\n\n这是一个知识库项目。\n\n## 功能介绍\n\n- 文档解析\n- 混合检索\n"
    file_path = tmp_path / "document.md"
    file_path.write_text(content, encoding="utf-8")

    result = await parser.parse(file_path)

    assert isinstance(result, ParsedDocument)
    assert result.content == content
    assert result.file_type == "md"
    assert result.metadata["encoding"] == "utf-8-sig"
    assert result.metadata["char_count"] == len(content)
    assert result.metadata["line_count"] == len(content.splitlines())
    assert result.warnings == ()


@pytest.mark.asyncio
async def test_markdown_parser_preserves_markdown_syntax(parser, tmp_path):
    """测试保留 Markdown 标题、链接、代码块等原始语法。"""
    content = (
        "# 标题\n\n[项目链接](https://example.com)\n\n```python\nprint('KnowledgeFlow')\n```\n"
    )
    file_path = tmp_path / "syntax.md"
    file_path.write_text(content, encoding="utf-8")

    result = await parser.parse(file_path)

    assert result.content == content
    assert "```python" in result.content
    assert "[项目链接](https://example.com)" in result.content


@pytest.mark.asyncio
async def test_markdown_parser_supports_utf8_bom(parser, tmp_path):
    """测试支持带 UTF-8 BOM 的 Markdown 文件。"""
    content = "# UTF-8 BOM 测试\n\n文档内容"
    file_path = tmp_path / "bom.md"
    file_path.write_text(content, encoding="utf-8-sig")

    result = await parser.parse(file_path)

    assert result.content == content
    assert not result.content.startswith("\ufeff")


@pytest.mark.asyncio
async def test_markdown_parser_preserves_newlines(parser, tmp_path):
    """测试保留 CRLF 和 LF 等原始换行符。"""
    content = "# 第一行\r\n第二行\n第三行\r\n"
    file_path = tmp_path / "newlines.md"
    file_path.write_bytes(content.encode("utf-8"))

    result = await parser.parse(file_path)

    assert result.content == content
    assert result.metadata["line_count"] == 3


@pytest.mark.asyncio
async def test_markdown_parser_supports_uppercase_extension(parser, tmp_path):
    """测试支持大写 MD 扩展名。"""
    file_path = tmp_path / "document.MD"
    file_path.write_text("# 测试", encoding="utf-8")

    result = await parser.parse(file_path)

    assert result.file_type == "md"
    assert result.content == "# 测试"


@pytest.mark.asyncio
async def test_markdown_parser_supports_empty_content(parser, tmp_path):
    """测试支持空 Markdown 文件。"""
    file_path = tmp_path / "empty.md"
    file_path.write_bytes(b"")

    result = await parser.parse(file_path)

    assert result.content == ""
    assert result.metadata["char_count"] == 0
    assert result.metadata["line_count"] == 0


@pytest.mark.asyncio
async def test_markdown_parser_rejects_unsupported_extension(parser, tmp_path):
    """测试拒绝不支持的文件扩展名。"""
    file_path = tmp_path / "document.txt"
    file_path.write_text("测试内容", encoding="utf-8")

    with pytest.raises(UnsupportedFileTypeError):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_markdown_parser_rejects_missing_file(parser, tmp_path):
    """测试文件不存在时抛出解析异常。"""
    file_path = tmp_path / "missing.md"

    with pytest.raises(DocumentParseError, match="不存在"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_markdown_parser_rejects_directory(parser, tmp_path):
    """测试拒绝将目录作为 Markdown 文件解析。"""
    directory = tmp_path / "document.md"
    directory.mkdir()

    with pytest.raises(DocumentParseError, match="普通文件"):
        await parser.parse(directory)


@pytest.mark.asyncio
async def test_markdown_parser_rejects_invalid_encoding(parser, tmp_path):
    """测试拒绝无效 UTF-8 编码。"""
    file_path = tmp_path / "invalid.md"
    file_path.write_bytes(b"\xff\xfe\xfa")

    with pytest.raises(DocumentParseError, match="UTF-8"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_markdown_parser_wraps_read_error(parser, tmp_path, monkeypatch):
    """测试将文件读取异常转换为统一解析异常。"""
    file_path = tmp_path / "document.md"
    file_path.write_text("# 测试", encoding="utf-8")

    def raise_read_error(*args, **kwargs):
        raise OSError("模拟磁盘读取失败")

    monkeypatch.setattr(type(file_path), "open", raise_read_error)

    with pytest.raises(DocumentParseError, match="读取失败"):
        await parser.parse(file_path)


@pytest.mark.asyncio
async def test_markdown_parser_uses_thread_for_file_reading(parser, tmp_path, monkeypatch):
    """测试文件读取通过线程池执行。"""
    file_path = tmp_path / "document.md"
    file_path.write_text("# 测试", encoding="utf-8")

    original_to_thread = asyncio.to_thread
    called = False

    async def track_to_thread(func, *args, **kwargs):
        nonlocal called
        called = True
        return await original_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", track_to_thread)

    result = await parser.parse(file_path)

    assert called is True
    assert result.content == "# 测试"
