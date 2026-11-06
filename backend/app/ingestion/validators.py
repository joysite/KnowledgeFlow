"""KnowledgeFlow 上传文件安全校验模块。"""

import codecs
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path


class FileValidationError(ValueError):
    """上传文件校验失败。"""


@dataclass(frozen=True, slots=True)
class ValidatedFile:
    """通过校验的文件信息。"""

    filename: str
    file_type: str
    file_size: int
    content_type: str


class UploadFileValidator:
    """负责上传文件的名称、类型、大小和内容校验。"""

    ALLOWED_EXTENSIONS = frozenset({"pdf", "docx", "md", "txt"})

    MIME_TYPES = {
        "pdf": frozenset({"application/pdf"}),
        "docx": frozenset(
            {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
        ),
        "md": frozenset(
            {
                "text/markdown",
                "text/x-markdown",
                "text/plain",
            }
        ),
        "txt": frozenset({"text/plain"}),
    }

    GENERIC_MIME_TYPES = frozenset(
        {
            "",
            "application/octet-stream",
            "binary/octet-stream",
        }
    )

    TEXT_CHUNK_SIZE = 64 * 1024

    # DOCX ZIP 安全限制
    DOCX_MAX_ENTRIES = 10_000
    DOCX_MAX_TOTAL_UNCOMPRESSED_SIZE = 100 * 1024 * 1024
    DOCX_MAX_SINGLE_FILE_SIZE = 50 * 1024 * 1024
    DOCX_MAX_COMPRESSION_RATIO = 200
    DOCX_STREAM_READ_SIZE = 64 * 1024

    def __init__(self, max_size_bytes: int) -> None:
        """初始化校验器。"""
        if isinstance(max_size_bytes, bool) or not isinstance(max_size_bytes, int):
            raise ValueError("max_size_bytes 必须是正整数")

        if max_size_bytes <= 0:
            raise ValueError("max_size_bytes 必须大于 0")

        self.max_size_bytes = max_size_bytes

    @staticmethod
    def _validate_filename(filename: str) -> str:
        """校验原始文件名，禁止路径穿越和控制字符。"""
        if not isinstance(filename, str):
            raise FileValidationError("文件名必须是字符串")

        filename = filename.strip()

        if not filename:
            raise FileValidationError("文件名不能为空")

        if filename in {".", ".."}:
            raise FileValidationError("文件名无效")

        if "/" in filename or "\\" in filename or "\0" in filename:
            raise FileValidationError("文件名不能包含路径信息")

        if any(ord(char) < 32 or ord(char) == 127 for char in filename):
            raise FileValidationError("文件名不能包含控制字符")

        if Path(filename).name != filename:
            raise FileValidationError("文件名无效")

        return filename

    def _validate_extension(self, filename: str) -> str:
        """校验文件扩展名。"""
        suffix = Path(filename).suffix.lower().lstrip(".")

        if suffix not in self.ALLOWED_EXTENSIONS:
            raise FileValidationError(f"不支持的文件类型：{suffix or '无扩展名'}")

        return suffix

    def _validate_mime_type(self, file_type: str, content_type: str | None) -> str:
        """校验客户端提供的 MIME 类型。"""
        mime_type = (content_type or "").split(";", maxsplit=1)[0].strip().lower()

        if mime_type in self.GENERIC_MIME_TYPES:
            return mime_type or "application/octet-stream"

        allowed_types = self.MIME_TYPES[file_type]

        if mime_type not in allowed_types:
            raise FileValidationError(f"MIME 类型与文件扩展名不匹配：{mime_type}")

        return mime_type

    def _validate_pdf(self, file_path: Path) -> None:
        """检查 PDF 文件头。"""
        with file_path.open("rb") as file:
            header = file.read(1024)

        if b"%PDF-" not in header:
            raise FileValidationError("文件内容不是有效的 PDF 文件")

    def _validate_docx_stream(self, archive, infos) -> None:
        """流式读取 ZIP 条目，限制实际解压的数据量。"""
        total_uncompressed_size = 0

        for info in infos:
            entry_uncompressed_size = 0

            with archive.open(info, "r") as entry:
                while True:
                    chunk = entry.read(self.DOCX_STREAM_READ_SIZE)
                    if not chunk:
                        break

                    actual_size = len(chunk)
                    entry_uncompressed_size += actual_size
                    total_uncompressed_size += actual_size

                    if entry_uncompressed_size > self.DOCX_MAX_SINGLE_FILE_SIZE:
                        raise FileValidationError("DOCX 文件内部单个文件实际解压大小超过限制")

                    if total_uncompressed_size > self.DOCX_MAX_TOTAL_UNCOMPRESSED_SIZE:
                        raise FileValidationError("DOCX 文件实际总解压大小超过限制")

    def _validate_docx(self, file_path: Path) -> None:
        """检查 DOCX ZIP 容器、内部结构及解压资源限制。"""
        if not zipfile.is_zipfile(file_path):
            raise FileValidationError("DOCX 文件不是有效的 ZIP 容器")

        try:
            with zipfile.ZipFile(file_path, "r") as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]

                required_files = {
                    "[Content_Types].xml",
                    "word/document.xml",
                }

                if not required_files.issubset(names):
                    raise FileValidationError("DOCX 文件缺少必要的内部结构")

                if len(infos) > self.DOCX_MAX_ENTRIES:
                    raise FileValidationError("DOCX 文件内部条目数量异常")

                if len(names) != len(set(names)):
                    raise FileValidationError("DOCX 文件包含重复的内部文件名")

                if any(info.flag_bits & 0x1 for info in infos):
                    raise FileValidationError("不支持加密的 DOCX 文件")

                total_uncompressed_size = 0

                for info in infos:
                    if info.file_size < 0 or info.compress_size < 0:
                        raise FileValidationError("DOCX 文件包含无效的 ZIP 大小信息")

                    if info.file_size > self.DOCX_MAX_SINGLE_FILE_SIZE:
                        raise FileValidationError("DOCX 文件内部单个文件解压大小超过限制")

                    total_uncompressed_size += info.file_size

                    if total_uncompressed_size > self.DOCX_MAX_TOTAL_UNCOMPRESSED_SIZE:
                        raise FileValidationError("DOCX 文件总解压大小超过限制")

                    if info.file_size > 0:
                        if info.compress_size == 0:
                            raise FileValidationError("DOCX 文件包含异常压缩数据")

                        if info.file_size > info.compress_size * self.DOCX_MAX_COMPRESSION_RATIO:
                            raise FileValidationError("DOCX 文件压缩比异常")

                # 元数据检查通过后，再实际读取所有条目验证解压大小。
                self._validate_docx_stream(archive, infos)

        except (
            OSError,
            EOFError,
            RuntimeError,
            NotImplementedError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
            zlib.error,
        ) as exc:
            raise FileValidationError("DOCX 文件结构损坏") from exc

    def _validate_text(self, file_path: Path) -> None:
        """使用增量解码验证 UTF-8 文本，避免一次性加载整个文件。"""
        decoder = codecs.getincrementaldecoder("utf-8-sig")("strict")

        try:
            with file_path.open("rb") as file:
                while chunk := file.read(self.TEXT_CHUNK_SIZE):
                    if b"\0" in chunk:
                        raise FileValidationError("TXT/Markdown 文件不能包含 NUL 字节")

                    decoder.decode(chunk, final=False)

                decoder.decode(b"", final=True)

        except UnicodeDecodeError as exc:
            raise FileValidationError("TXT/Markdown 文件必须使用 UTF-8 或 UTF-8 BOM 编码") from exc

    def validate(
        self,
        filename: str,
        file_path: str | Path,
        content_type: str | None = None,
    ) -> ValidatedFile:
        """
        校验上传文件。

        Args:
            filename: 用户上传时提供的原始文件名。
            file_path: 已保存到临时位置的文件路径。
            content_type: 客户端提供的 MIME 类型，仅作为辅助校验信息。

        Returns:
            标准化后的文件信息。

        Raises:
            FileValidationError: 文件不符合安全校验要求。
        """
        safe_filename = self._validate_filename(filename)
        file_type = self._validate_extension(safe_filename)
        normalized_mime = self._validate_mime_type(file_type, content_type)

        path = Path(file_path)

        if not path.exists() or not path.is_file():
            raise FileValidationError("上传文件不存在或不是普通文件")

        try:
            file_size = path.stat().st_size
        except OSError as exc:
            raise FileValidationError("无法读取上传文件信息") from exc

        if file_size <= 0:
            raise FileValidationError("不允许上传空文件")

        if file_size > self.max_size_bytes:
            raise FileValidationError(f"文件大小超过限制，最大允许 {self.max_size_bytes} 字节")

        if file_type == "pdf":
            self._validate_pdf(path)
        elif file_type == "docx":
            self._validate_docx(path)
        else:
            self._validate_text(path)

        return ValidatedFile(
            filename=safe_filename,
            file_type=file_type,
            file_size=file_size,
            content_type=normalized_mime,
        )
