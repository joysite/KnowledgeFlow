"""KnowledgeFlow DOCX 文档解析器。"""

import asyncio
from pathlib import Path
from zipfile import BadZipFile

from docx import Document as WordDocument
from docx.opc.exceptions import PackageNotFoundError
from lxml.etree import XMLSyntaxError

from app.ingestion.parsers.base import (
    BaseParser,
    DocumentParseError,
    ParsedDocument,
    UnsupportedFileTypeError,
)


class DOCXParser(BaseParser):
    """负责提取 DOCX 文档中的段落和表格文本。"""

    @staticmethod
    def _read_file(path: Path) -> tuple[str, int, int]:
        """读取 DOCX 正文，按照文档顺序提取段落和表格。"""
        document = WordDocument(str(path))

        content_blocks: list[str] = []
        paragraph_count = 0
        table_count = 0

        for block in document.iter_inner_content():
            if hasattr(block, "text"):
                # 提取正文段落。
                paragraph_count += 1
                text = block.text

                if text.strip():
                    content_blocks.append(text)

            else:
                # 提取表格，单元格之间使用制表符分隔。
                table_count += 1
                table = block

                for row in table.rows:
                    cells = [cell.text for cell in row.cells]

                    if any(cell.strip() for cell in cells):
                        content_blocks.append("\t".join(cells))

        content = "\n".join(content_blocks)

        return content, paragraph_count, table_count

    async def parse(self, file_path: Path) -> ParsedDocument:
        """
        异步解析 DOCX 文档。

        Args:
            file_path: DOCX 文件路径。

        Returns:
            包含正文、段落数量、表格数量和解析警告的结果。

        Raises:
            UnsupportedFileTypeError: 文件扩展名不是 DOCX。
            DocumentParseError: 文件不存在、损坏或读取失败。
        """
        path = Path(file_path)

        if path.suffix.lower() != ".docx":
            raise UnsupportedFileTypeError(
                f"DOCX 解析器不支持该文件类型：{path.suffix or '无扩展名'}"
            )

        try:
            if not path.exists() or not path.is_file():
                raise DocumentParseError("DOCX 文件不存在或不是普通文件")

            content, paragraph_count, table_count = await asyncio.to_thread(
                self._read_file,
                path,
            )

        except DocumentParseError:
            raise
        except (
            BadZipFile,
            PackageNotFoundError,
            XMLSyntaxError,
            OSError,
            ValueError,
            KeyError,
        ) as exc:
            raise DocumentParseError("DOCX 文件损坏或读取失败") from exc

        warnings: list[str] = []

        if not content.strip():
            warnings.append("DOCX 文档没有提取到可用文本")

        return ParsedDocument(
            content=content,
            file_type="docx",
            metadata={
                "paragraph_count": paragraph_count,
                "table_count": table_count,
                "char_count": len(content),
            },
            warnings=tuple(warnings),
        )
