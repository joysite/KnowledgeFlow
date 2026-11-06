"""KnowledgeFlow 本地文件存储模块。"""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import aiofiles
from starlette.datastructures import UploadFile

from app.core.config import get_settings
from app.core.paths import UPLOAD_DIR


class FileStorageError(Exception):
    """文件存储操作失败。"""


class UploadTooLargeError(FileStorageError):
    """上传文件超过大小限制。"""


@dataclass(frozen=True, slots=True)
class StoredFile:
    """成功保存的文件信息。"""

    file_path: str
    file_size: int
    content_hash: str
    original_filename: str


class LocalFileStorage:
    """负责上传文件的本地安全存储与删除。"""

    CHUNK_SIZE = 1024 * 1024
    ALLOWED_EXTENSIONS = frozenset({"pdf", "docx", "md", "txt"})

    def __init__(
        self,
        upload_dir: str | Path = UPLOAD_DIR,
        max_size_bytes: int | None = None,
    ) -> None:
        """初始化本地文件存储。"""
        if max_size_bytes is None:
            max_size_bytes = get_settings().max_upload_size_bytes

        if (
            isinstance(max_size_bytes, bool)
            or not isinstance(max_size_bytes, int)
            or max_size_bytes <= 0
        ):
            raise ValueError("max_size_bytes 必须是正整数")

        self.upload_dir = Path(upload_dir).resolve()
        self.max_size_bytes = max_size_bytes

    @staticmethod
    def _get_extension(filename: str | None) -> str:
        """获取并校验文件扩展名。"""
        if not isinstance(filename, str) or not filename.strip():
            raise FileStorageError("上传文件必须提供有效文件名")

        extension = Path(filename).suffix.lower().lstrip(".")

        if extension not in LocalFileStorage.ALLOWED_EXTENSIONS:
            raise FileStorageError("不支持的文件扩展名")

        return extension

    def _ensure_upload_dir(self) -> None:
        """创建上传目录并确认其为目录。"""
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        if not self.upload_dir.is_dir():
            raise FileStorageError("上传存储路径不是有效目录")

    async def save(self, upload_file: UploadFile) -> StoredFile:
        """
        分块保存上传文件并计算 SHA-256。

        先写入上传目录中的临时文件，完成后再原子重命名。
        超过大小限制或发生异常时自动清理临时文件。

        Args:
            upload_file: Starlette 上传文件对象。

        Returns:
            已保存文件的路径、大小、SHA-256 和原始文件名。

        Raises:
            FileStorageError: 文件存储失败。
            UploadTooLargeError: 文件超过大小限制。
        """
        if not isinstance(upload_file, UploadFile):
            raise TypeError("upload_file 必须是 Starlette UploadFile")

        original_filename = upload_file.filename
        extension = self._get_extension(original_filename)

        self._ensure_upload_dir()

        final_path = self.upload_dir / f"{uuid4().hex}.{extension}"
        temp_path: Path | None = None

        try:
            # 在目标目录内创建临时文件，确保后续原子重命名位于同一文件系统。
            file_descriptor, temp_name = tempfile.mkstemp(
                prefix=".upload-",
                suffix=".tmp",
                dir=self.upload_dir,
            )
            os.close(file_descriptor)
            temp_path = Path(temp_name)

            digest = hashlib.sha256()
            total_size = 0

            await upload_file.seek(0)

            async with aiofiles.open(temp_path, "wb") as destination:
                while chunk := await upload_file.read(self.CHUNK_SIZE):
                    total_size += len(chunk)

                    if total_size > self.max_size_bytes:
                        raise UploadTooLargeError(
                            f"上传文件超过大小限制，最大允许 {self.max_size_bytes} 字节"
                        )

                    digest.update(chunk)
                    await destination.write(chunk)

            if total_size == 0:
                raise FileStorageError("不允许保存空文件")

            # 原子发布文件，避免其他模块读取到未写完的文件。
            os.replace(temp_path, final_path)
            temp_path = None

            return StoredFile(
                file_path=str(final_path),
                file_size=total_size,
                content_hash=digest.hexdigest(),
                original_filename=original_filename,
            )

        except BaseException:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

            # 如果正式文件发布后发生异常，也清理本次生成的文件。
            final_path.unlink(missing_ok=True)
            raise

    async def delete(self, file_path: str | Path) -> bool:
        """
        删除上传目录内的文件。

        只允许删除上传目录的直接子文件，不允许删除目录、
        符号链接或上传目录以外的路径。

        Args:
            file_path: 待删除文件的路径。

        Returns:
            文件存在且成功删除时返回 True，否则返回 False。

        Raises:
            FileStorageError: 路径不属于受管理的上传文件。
        """
        try:
            target = Path(file_path)
        except TypeError as exc:
            raise FileStorageError("文件路径无效") from exc

        if target.is_symlink():
            raise FileStorageError("不允许删除符号链接")

        try:
            resolved_target = target.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise FileStorageError("无法解析文件路径") from exc

        if resolved_target.parent != self.upload_dir:
            raise FileStorageError("禁止删除上传目录以外的文件")

        if resolved_target == self.upload_dir:
            raise FileStorageError("禁止删除上传目录本身")

        if resolved_target.exists() and not resolved_target.is_file():
            raise FileStorageError("只能删除普通文件")

        if not resolved_target.exists():
            return False

        try:
            resolved_target.unlink()
        except OSError as exc:
            raise FileStorageError("删除上传文件失败") from exc

        return True
