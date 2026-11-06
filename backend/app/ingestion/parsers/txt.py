"""KnowledgeFlow TXT 文档解析器。"""

import asyncio
from pathlib import Path

from app.ingestion.parsers.base import (
    BaseParser,
    DocumentParseError,
    ParsedDocument,
    UnsupportedFileTypeError,
)


class TXTParser(BaseParser):
    """负责解析 UTF-8 编码的 TXT 文档。"""

    @staticmethod
    def _read_file(path: Path) -> str:
        """读取 TXT 文件并保留原始换行符。"""
        with path.open(
            mode="r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            return file.read()

    async def parse(self, file_path: Path) -> ParsedDocument:
        """
        异步解析 TXT 文档。

        Args:
            file_path: TXT 文件路径。

        Returns:
            统一格式的文档解析结果。

        Raises:
            UnsupportedFileTypeError: 文件扩展名不是 TXT。
            DocumentParseError: 文件不存在、读取失败或编码无效。
        """
        path = Path(file_path)

        if path.suffix.lower() != ".txt":
            raise UnsupportedFileTypeError(
                f"TXT 解析器不支持该文件类型：{path.suffix or '无扩展名'}"
            )

        try:
            if not path.exists() or not path.is_file():
                raise DocumentParseError("TXT 文件不存在或不是普通文件")

            content = await asyncio.to_thread(self._read_file, path)

        except UnicodeDecodeError as exc:
            raise DocumentParseError("TXT 文件必须使用 UTF-8 或 UTF-8 BOM 编码") from exc
        except OSError as exc:
            raise DocumentParseError("TXT 文件读取失败") from exc

        return ParsedDocument(
            content=content,
            file_type="txt",
            metadata={
                "encoding": "utf-8-sig",
                "char_count": len(content),
                "line_count": len(content.splitlines()),
            },
        )
