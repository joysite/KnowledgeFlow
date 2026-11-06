"""KnowledgeFlow 文档解析器基础接口。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ParserError(Exception):
    """文档解析基础异常。"""


class UnsupportedFileTypeError(ParserError):
    """不支持的文档类型。"""


class DocumentParseError(ParserError):
    """文档内容解析失败。"""


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """统一的文档解析结果。"""

    content: str
    file_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """校验解析结果的基本数据类型。"""
        if not isinstance(self.content, str):
            raise TypeError("content 必须是字符串")

        if not isinstance(self.file_type, str) or not self.file_type.strip():
            raise ValueError("file_type 不能为空")

        if not isinstance(self.metadata, dict):
            raise TypeError("metadata 必须是字典")

        if not isinstance(self.warnings, tuple):
            raise TypeError("warnings 必须是字符串元组")

        if not all(isinstance(item, str) for item in self.warnings):
            raise TypeError("warnings 中的元素必须是字符串")

        object.__setattr__(self, "file_type", self.file_type.strip().lower())


class BaseParser(ABC):
    """所有文档解析器的抽象基类。"""

    @abstractmethod
    async def parse(self, file_path: Path) -> ParsedDocument:
        """
        异步解析文档。

        Args:
            file_path: 待解析文档的本地路径。

        Returns:
            统一格式的文档解析结果。

        Raises:
            DocumentParseError: 文档解析失败。
            UnsupportedFileTypeError: 文档类型不受支持。
        """
        raise NotImplementedError
