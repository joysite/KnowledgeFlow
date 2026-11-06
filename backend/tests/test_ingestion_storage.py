"""KnowledgeFlow 本地文件存储模块测试。"""

import asyncio
import hashlib
import io
from pathlib import Path

import pytest
from fastapi import UploadFile

from app.ingestion.storage import (
    FileStorageError,
    LocalFileStorage,
    StoredFile,
    UploadTooLargeError,
)


@pytest.fixture
def upload_dir(tmp_path):
    """创建独立的上传测试目录。"""
    return tmp_path / "uploads"


@pytest.fixture
def storage(upload_dir):
    """创建默认文件存储实例。"""
    return LocalFileStorage(
        upload_dir=upload_dir,
        max_size_bytes=1024 * 1024,
    )


def make_upload_file(
    content: bytes,
    filename: str = "test.txt",
) -> UploadFile:
    """构造 FastAPI 上传文件对象。"""
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
    )


def test_storage_initialization(storage, upload_dir):
    """测试存储初始化。"""
    assert storage.upload_dir == upload_dir.resolve()
    assert storage.max_size_bytes == 1024 * 1024


@pytest.mark.parametrize("size", [0, -1, True, 1.5, "1024"])
def test_storage_rejects_invalid_max_size(upload_dir, size):
    """测试拒绝非法上传大小配置。"""
    with pytest.raises(ValueError):
        LocalFileStorage(upload_dir, size)


@pytest.mark.parametrize(
    "filename",
    [
        None,
        "",
        " ",
        "test.exe",
        "test",
        "test.pdf.exe",
    ],
)
@pytest.mark.asyncio
async def test_storage_rejects_invalid_filename(storage, filename):
    """测试拒绝无效文件名和扩展名。"""
    upload = make_upload_file(b"content", filename)

    with pytest.raises(FileStorageError):
        await storage.save(upload)


@pytest.mark.asyncio
async def test_storage_saves_txt_file(storage, upload_dir):
    """测试成功保存 TXT 文件。"""
    content = "KnowledgeFlow 文档存储测试".encode()
    upload = make_upload_file(content, "测试文档.txt")

    result = await storage.save(upload)

    assert isinstance(result, StoredFile)
    assert result.original_filename == "测试文档.txt"
    assert result.file_size == len(content)
    assert result.content_hash == hashlib.sha256(content).hexdigest()

    saved_path = Path(result.file_path)

    assert saved_path.is_file()
    assert saved_path.parent == upload_dir.resolve()
    assert saved_path.suffix == ".txt"
    assert saved_path.read_bytes() == content
    assert saved_path.name != result.original_filename


@pytest.mark.asyncio
async def test_storage_uses_uuid_filename(storage):
    """测试磁盘文件名使用 UUID，而不是用户文件名。"""
    upload = make_upload_file(b"content", "../../dangerous.txt")

    result = await storage.save(upload)

    filename = Path(result.file_path).name

    assert filename.endswith(".txt")
    assert len(filename.removesuffix(".txt")) == 32
    assert "/" not in filename
    assert "\\" not in filename


@pytest.mark.asyncio
async def test_storage_computes_sha256(storage):
    """测试上传过程中正确计算 SHA-256。"""
    content = b"KnowledgeFlow SHA256"
    upload = make_upload_file(content)

    result = await storage.save(upload)

    assert result.content_hash == hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_storage_rejects_empty_file(storage, upload_dir):
    """测试拒绝空文件。"""
    upload = make_upload_file(b"")

    with pytest.raises(FileStorageError, match="空文件"):
        await storage.save(upload)

    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_storage_rejects_oversized_file(upload_dir):
    """测试超过限制时拒绝保存并清理临时文件。"""
    storage = LocalFileStorage(upload_dir, max_size_bytes=4)
    upload = make_upload_file(b"12345")

    with pytest.raises(UploadTooLargeError):
        await storage.save(upload)

    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_storage_cleans_temp_file_when_upload_is_cancelled(
    storage,
    upload_dir,
    monkeypatch,
):
    """测试上传任务取消时清理临时文件。"""
    upload = make_upload_file(b"content")

    async def cancel_read(size: int = -1) -> bytes:
        raise asyncio.CancelledError

    monkeypatch.setattr(upload, "read", cancel_read)

    with pytest.raises(asyncio.CancelledError):
        await storage.save(upload)

    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_storage_accepts_file_at_exact_size_limit(upload_dir):
    """测试刚好达到大小限制的文件可以保存。"""
    storage = LocalFileStorage(upload_dir, max_size_bytes=4)
    upload = make_upload_file(b"1234")

    result = await storage.save(upload)

    assert result.file_size == 4
    assert Path(result.file_path).read_bytes() == b"1234"


@pytest.mark.asyncio
async def test_storage_creates_upload_directory(tmp_path):
    """测试上传目录不存在时自动创建。"""
    upload_dir = tmp_path / "nested" / "uploads"
    storage = LocalFileStorage(upload_dir, max_size_bytes=1024)

    result = await storage.save(make_upload_file(b"content"))

    assert upload_dir.is_dir()
    assert Path(result.file_path).is_file()


@pytest.mark.asyncio
async def test_storage_does_not_leave_temp_file_after_success(storage, upload_dir):
    """测试成功保存后不存在临时文件。"""
    await storage.save(make_upload_file(b"content"))

    files = list(upload_dir.iterdir())

    assert len(files) == 1
    assert files[0].suffix == ".txt"


@pytest.mark.asyncio
async def test_storage_delete_existing_file(storage):
    """测试删除已保存的文件。"""
    result = await storage.save(make_upload_file(b"content"))

    assert await storage.delete(result.file_path) is True
    assert not Path(result.file_path).exists()


@pytest.mark.asyncio
async def test_storage_delete_missing_file(storage, upload_dir):
    """测试删除不存在的文件返回 False。"""
    missing_path = upload_dir / "missing.txt"

    assert await storage.delete(missing_path) is False


@pytest.mark.asyncio
async def test_storage_rejects_delete_outside_upload_dir(storage, tmp_path):
    """测试禁止删除上传目录以外的文件。"""
    outside_file = tmp_path / "important.txt"
    outside_file.write_text("important", encoding="utf-8")

    with pytest.raises(FileStorageError, match="上传目录以外"):
        await storage.delete(outside_file)

    assert outside_file.exists()


@pytest.mark.asyncio
async def test_storage_rejects_delete_upload_directory(storage, upload_dir):
    """测试禁止删除上传目录本身。"""
    upload_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(FileStorageError):
        await storage.delete(upload_dir)


@pytest.mark.asyncio
async def test_storage_rejects_delete_directory_inside_upload_dir(
    storage,
    upload_dir,
):
    """测试禁止删除上传目录内部的子目录。"""
    subdirectory = upload_dir / "nested"
    subdirectory.mkdir(parents=True)

    with pytest.raises(FileStorageError, match="普通文件"):
        await storage.delete(subdirectory)


@pytest.mark.asyncio
async def test_storage_rejects_delete_symlink(storage, upload_dir, tmp_path):
    """测试禁止通过符号链接删除文件。"""
    upload_dir.mkdir(parents=True, exist_ok=True)

    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("important", encoding="utf-8")

    symlink = upload_dir / "link.txt"
    symlink.symlink_to(outside_file)

    with pytest.raises(FileStorageError, match="符号链接"):
        await storage.delete(symlink)

    assert outside_file.exists()
    assert symlink.is_symlink()


@pytest.mark.asyncio
async def test_storage_rejects_invalid_upload_object(storage):
    """测试拒绝非 UploadFile 对象。"""
    with pytest.raises(TypeError):
        await storage.save(b"not an upload file")


@pytest.mark.asyncio
async def test_storage_accepts_all_supported_extensions(storage):
    """测试支持的扩展名均可保存。"""
    for extension in ("pdf", "docx", "md", "txt"):
        upload = make_upload_file(b"content", f"test.{extension}")
        result = await storage.save(upload)

        assert Path(result.file_path).suffix == f".{extension}"
