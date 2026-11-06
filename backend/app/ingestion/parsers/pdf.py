"""KnowledgeFlow PDF 文档解析器。"""

import asyncio
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import Settings, get_settings
from app.ingestion.parsers.base import (
    BaseParser,
    DocumentParseError,
    ParsedDocument,
    UnsupportedFileTypeError,
)


class PDFParser(BaseParser):
    """负责提取 PDF 文档的文本内容，并限制解析资源消耗。"""

    def __init__(self, settings: Settings | None = None) -> None:
        """初始化 PDF 解析器及资源限制。"""
        if settings is not None and not isinstance(settings, Settings):
            raise TypeError("settings 必须是 Settings 实例")

        self.settings = settings if settings is not None else get_settings()

    def _read_file(
        self,
        path: Path,
    ) -> tuple[list[dict[str, Any]], int, list[int]]:
        """读取 PDF 并在逐页提取过程中执行资源限制。"""
        pages: list[dict[str, Any]] = []
        extraction_failures: list[int] = []
        total_chars = 0

        with path.open("rb") as file:
            reader = PdfReader(file, strict=True)

            if reader.is_encrypted:
                raise DocumentParseError("暂不支持解析加密 PDF 文件")

            page_count = len(reader.pages)

            if page_count > self.settings.pdf_max_pages:
                raise DocumentParseError(
                    f"PDF 页面数量超过限制，最大允许 "
                    f"{self.settings.pdf_max_pages} 页，实际 {page_count} 页"
                )

            for page_number, page in enumerate(reader.pages, start=1):
                try:
                    content = page.extract_text() or ""
                except Exception:
                    content = ""
                    extraction_failures.append(page_number)

                page_chars = len(content)

                if page_chars > self.settings.pdf_max_page_chars:
                    raise DocumentParseError(
                        f"PDF 第 {page_number} 页文本长度超过限制，"
                        f"最大允许 {self.settings.pdf_max_page_chars} 字符，"
                        f"实际 {page_chars} 字符"
                    )

                # 最终全文使用换行符连接页面，累计时也计算分隔符。
                separator_chars = 1 if pages else 0
                next_total_chars = total_chars + separator_chars + page_chars

                if next_total_chars > self.settings.pdf_max_total_chars:
                    raise DocumentParseError(
                        "PDF 全文文本长度超过限制，最大允许 "
                        f"{self.settings.pdf_max_total_chars} 字符"
                    )

                total_chars = next_total_chars

                pages.append(
                    {
                        "page_number": page_number,
                        "content": content,
                        "char_count": page_chars,
                    }
                )

        return pages, page_count, extraction_failures

    async def parse(self, file_path: Path) -> ParsedDocument:
        """
        异步解析 PDF 文档。

        Args:
            file_path: PDF 文件路径。

        Returns:
            包含全文、页码信息和解析警告的结果。

        Raises:
            UnsupportedFileTypeError: 文件扩展名不是 PDF。
            DocumentParseError: 文件不存在、损坏、加密或超过资源限制。
        """
        path = Path(file_path)

        if path.suffix.lower() != ".pdf":
            raise UnsupportedFileTypeError(
                f"PDF 解析器不支持该文件类型：{path.suffix or '无扩展名'}"
            )

        try:
            if not path.exists() or not path.is_file():
                raise DocumentParseError("PDF 文件不存在或不是普通文件")

            pages, page_count, extraction_failures = await asyncio.to_thread(
                self._read_file,
                path,
            )

        except DocumentParseError:
            raise
        except (PdfReadError, OSError, ValueError) as exc:
            raise DocumentParseError("PDF 文件损坏或读取失败") from exc

        warnings: list[str] = []
        failed_pages = set(extraction_failures)

        for page in pages:
            page_number = page["page_number"]

            if page_number in failed_pages:
                warnings.append(f"第 {page_number} 页文本提取失败，已跳过该页")
            elif not page["content"].strip():
                warnings.append(f"第 {page_number} 页未提取到文本，可能是空白页或扫描页面")

        content = "\n".join(page["content"] for page in pages)

        if page_count == 0:
            warnings.append("PDF 文档没有页面")
        elif not any(page["content"].strip() for page in pages) and not extraction_failures:
            warnings.append("未提取到可用文本，扫描版 PDF 需要 OCR 才能识别")

        return ParsedDocument(
            content=content,
            file_type="pdf",
            metadata={
                "page_count": page_count,
                "pages": pages,
                "char_count": len(content),
            },
            warnings=tuple(warnings),
        )
