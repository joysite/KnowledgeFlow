"""文档解析器注册表测试。"""

from pathlib import Path

import pytest

from app.ingestion.parsers.base import (
    BaseParser,
    UnsupportedFileTypeError,
)
from app.ingestion.parsers.docx import DOCXParser
from app.ingestion.parsers.markdown import MarkdownParser
from app.ingestion.parsers.pdf import PDFParser
from app.ingestion.parsers.registry import ParserRegistry
from app.ingestion.parsers.txt import TXTParser


@pytest.fixture
def registry() -> ParserRegistry:
    """创建默认解析器注册表。"""
    return ParserRegistry()


def test_registry_registers_builtin_parsers(registry):
    """验证初始化时注册四种内置解析器。"""
    assert registry.supported_extensions == ("docx", "md", "pdf", "txt")


@pytest.mark.parametrize(
    ("extension", "parser_type"),
    [
        ("txt", TXTParser),
        ("md", MarkdownParser),
        ("pdf", PDFParser),
        ("docx", DOCXParser),
    ],
)
def test_registry_get_parser(registry, extension, parser_type):
    """验证根据扩展名获取正确的解析器。"""
    parser = registry.get_parser(extension)

    assert isinstance(parser, parser_type)
    assert isinstance(parser, BaseParser)


@pytest.mark.parametrize(
    ("file_path", "parser_type"),
    [
        ("document.txt", TXTParser),
        ("document.md", MarkdownParser),
        ("document.pdf", PDFParser),
        ("document.docx", DOCXParser),
        ("DOCUMENT.TXT", TXTParser),
        (Path("DOCUMENT.PDF"), PDFParser),
    ],
)
def test_registry_get_parser_for_file(registry, file_path, parser_type):
    """验证根据文件路径和大小写扩展名获取解析器。"""
    parser = registry.get_parser_for_file(file_path)

    assert isinstance(parser, parser_type)


def test_registry_supports_extension_with_dot(registry):
    """验证支持带点的扩展名。"""
    assert isinstance(registry.get_parser(".txt"), TXTParser)


def test_registry_rejects_unknown_extension(registry):
    """验证未知扩展名抛出统一异常。"""
    with pytest.raises(UnsupportedFileTypeError):
        registry.get_parser("xlsx")


def test_registry_rejects_file_without_extension(registry):
    """验证没有扩展名的文件。"""
    with pytest.raises(UnsupportedFileTypeError, match="没有扩展名"):
        registry.get_parser_for_file("README")


def test_registry_rejects_duplicate_registration(registry):
    """验证重复注册不会覆盖已有解析器。"""
    original_parser = registry.get_parser("txt")

    with pytest.raises(ValueError, match="已经注册"):
        registry.register("txt", MarkdownParser())

    assert registry.get_parser("txt") is original_parser


def test_registry_supports_custom_parser_registration(registry):
    """验证可以注册新的文件类型解析器。"""
    parser = MarkdownParser()

    registry.register("rst", parser)

    assert registry.get_parser("rst") is parser
    assert "rst" in registry.supported_extensions


def test_registry_rejects_invalid_parser():
    """验证拒绝没有实现 BaseParser 的对象。"""
    registry = ParserRegistry()

    with pytest.raises(TypeError, match="BaseParser"):
        registry.register("rst", object())


@pytest.mark.parametrize(
    "extension",
    [
        "",
        ".",
        "foo.bar",
        "foo/bar",
        "foo\\bar",
    ],
)
def test_registry_rejects_invalid_extension(registry, extension):
    """验证拒绝无效扩展名。"""
    with pytest.raises(ValueError, match="扩展名格式无效"):
        registry.get_parser(extension)


def test_registry_rejects_non_string_extension(registry):
    """验证拒绝非字符串扩展名。"""
    with pytest.raises(TypeError, match="必须是字符串"):
        registry.get_parser(None)


def test_registry_passes_settings_to_pdf_parser():
    """验证注册表将指定配置传递给 PDF 解析器。"""
    from app.core.config import Settings

    settings = Settings(
        pdf_max_pages=12,
        pdf_max_page_chars=100,
        pdf_max_total_chars=1000,
        _env_file=None,
    )

    registry = ParserRegistry(settings=settings)
    parser = registry.get_parser("pdf")

    assert isinstance(parser, PDFParser)
    assert parser.settings is settings
    assert parser.settings.pdf_max_pages == 12
    assert parser.settings.pdf_max_page_chars == 100
    assert parser.settings.pdf_max_total_chars == 1000


def test_registry_rejects_invalid_settings():
    """验证注册表拒绝无效配置对象。"""
    with pytest.raises(TypeError, match="Settings"):
        ParserRegistry(settings=object())
