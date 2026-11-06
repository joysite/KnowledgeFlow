"""KnowledgeFlow 文档解析器基类测试。"""

from pathlib import Path

import pytest

from app.ingestion.parsers.base import (
    BaseParser,
    DocumentParseError,
    ParsedDocument,
    ParserError,
    UnsupportedFileTypeError,
)


def test_parsed_document_initialization():
    """测试解析结果正常初始化。"""
    result = ParsedDocument(
        content="KnowledgeFlow 测试内容",
        file_type="TXT",
        metadata={"paragraph_count": 2},
        warnings=("存在空段落",),
    )

    assert result.content == "KnowledgeFlow 测试内容"
    assert result.file_type == "txt"
    assert result.metadata == {"paragraph_count": 2}
    assert result.warnings == ("存在空段落",)


def test_parsed_document_default_values():
    """测试解析结果默认字段。"""
    result = ParsedDocument(
        content="测试内容",
        file_type="md",
    )

    assert result.metadata == {}
    assert result.warnings == ()


def test_parsed_document_default_metadata_is_independent():
    """测试不同解析结果之间的默认 metadata 相互独立。"""
    first = ParsedDocument(content="内容一", file_type="txt")
    second = ParsedDocument(content="内容二", file_type="txt")

    first.metadata["source"] = "test"

    assert "source" not in second.metadata


def test_parsed_document_is_immutable():
    """测试解析结果对象不允许重新赋值。"""
    result = ParsedDocument(content="测试内容", file_type="txt")

    with pytest.raises(AttributeError):
        result.content = "修改后的内容"


@pytest.mark.parametrize(
    ("content", "file_type", "metadata", "warnings", "error"),
    [
        (123, "txt", {}, (), TypeError),
        ("内容", "", {}, (), ValueError),
        ("内容", "   ", {}, (), ValueError),
        ("内容", "txt", [], (), TypeError),
        ("内容", "txt", {}, [], TypeError),
        ("内容", "txt", {}, ("警告", 123), TypeError),
    ],
)
def test_parsed_document_rejects_invalid_values(
    content,
    file_type,
    metadata,
    warnings,
    error,
):
    """测试拒绝非法解析结果。"""
    with pytest.raises(error):
        ParsedDocument(
            content=content,
            file_type=file_type,
            metadata=metadata,
            warnings=warnings,
        )


def test_parser_exceptions_inherit_from_parser_error():
    """测试解析异常继承关系。"""
    assert issubclass(DocumentParseError, ParserError)
    assert issubclass(UnsupportedFileTypeError, ParserError)


def test_base_parser_cannot_be_instantiated():
    """测试抽象解析器不能直接实例化。"""
    with pytest.raises(TypeError):
        BaseParser()


def test_base_parser_requires_parse_implementation():
    """测试子类必须实现 parse 方法。"""

    class IncompleteParser(BaseParser):
        pass

    with pytest.raises(TypeError):
        IncompleteParser()


def test_base_parser_accepts_async_implementation():
    """测试子类可以实现异步解析接口。"""

    class DummyParser(BaseParser):
        async def parse(self, file_path: Path) -> ParsedDocument:
            return ParsedDocument(
                content="解析成功",
                file_type=file_path.suffix.lstrip("."),
            )

    parser = DummyParser()

    assert isinstance(parser, BaseParser)
    assert callable(parser.parse)
