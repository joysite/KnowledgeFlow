"""KnowledgeFlow 文档解析器注册表。"""

from pathlib import Path

from app.core.config import Settings, get_settings
from app.ingestion.parsers.base import (
    BaseParser,
    UnsupportedFileTypeError,
)
from app.ingestion.parsers.docx import DOCXParser
from app.ingestion.parsers.markdown import MarkdownParser
from app.ingestion.parsers.pdf import PDFParser
from app.ingestion.parsers.txt import TXTParser


class ParserRegistry:
    """根据文件扩展名管理和获取文档解析器。"""

    def __init__(self, settings: Settings | None = None) -> None:
        """初始化内置解析器注册表及其配置。"""
        if settings is not None and not isinstance(settings, Settings):
            raise TypeError("settings 必须是 Settings 实例")

        resolved_settings = settings if settings is not None else get_settings()
        self._parsers: dict[str, BaseParser] = {}

        self.register("txt", TXTParser())
        self.register("md", MarkdownParser())
        self.register("pdf", PDFParser(settings=resolved_settings))
        self.register("docx", DOCXParser())

    @staticmethod
    def _normalize_extension(extension: str) -> str:
        """统一文件扩展名格式。"""
        if not isinstance(extension, str):
            raise TypeError("文件扩展名必须是字符串")

        normalized = extension.strip().lower().lstrip(".")

        if not normalized or "." in normalized or "/" in normalized or "\\" in normalized:
            raise ValueError("文件扩展名格式无效")

        return normalized

    def register(self, extension: str, parser: BaseParser) -> None:
        """
        注册文档解析器。

        Args:
            extension: 文件扩展名，例如 txt 或 .txt。
            parser: 实现 BaseParser 接口的解析器。

        Raises:
            TypeError: 解析器没有实现 BaseParser 接口。
            ValueError: 扩展名无效或已经注册。
        """
        normalized = self._normalize_extension(extension)

        if not isinstance(parser, BaseParser):
            raise TypeError("parser 必须是 BaseParser 的实例")

        if normalized in self._parsers:
            raise ValueError(f"文件类型已经注册：{normalized}")

        self._parsers[normalized] = parser

    def get_parser(self, extension: str) -> BaseParser:
        """
        根据文件扩展名获取解析器。

        Args:
            extension: 文件扩展名，例如 txt 或 .txt。

        Returns:
            对应的文档解析器。

        Raises:
            UnsupportedFileTypeError: 没有对应的解析器。
        """
        normalized = self._normalize_extension(extension)
        parser = self._parsers.get(normalized)

        if parser is None:
            raise UnsupportedFileTypeError(f"没有注册对应的文档解析器：{normalized}")

        return parser

    def get_parser_for_file(self, file_path: str | Path) -> BaseParser:
        """
        根据文件路径获取解析器。

        Args:
            file_path: 文件路径。

        Returns:
            对应的文档解析器。
        """
        path = Path(file_path)

        if not path.suffix:
            raise UnsupportedFileTypeError("文件没有扩展名，无法选择解析器")

        return self.get_parser(path.suffix)

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        """返回已经注册的文件扩展名。"""
        return tuple(sorted(self._parsers))
