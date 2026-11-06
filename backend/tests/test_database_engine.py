"""KnowledgeFlow 异步数据库引擎测试。"""

import asyncio
from pathlib import Path

import pytest

from app.db.engine import create_database_engine


def test_create_database_engine_uses_async_sqlite(tmp_path: Path):
    """测试创建异步 SQLite 引擎。"""
    database_file = tmp_path / "nested" / "test.db"

    engine = create_database_engine(database_file)

    try:
        assert engine.url.drivername == "sqlite+aiosqlite"
        assert engine.url.database == str(database_file.resolve())
        assert database_file.parent.is_dir()
    finally:
        asyncio.run(engine.dispose())


def test_database_engine_enables_foreign_keys(tmp_path: Path):
    """测试数据库连接自动启用外键约束。"""
    database_file = tmp_path / "test.db"
    engine = create_database_engine(database_file)

    async def check_foreign_keys():
        try:
            async with engine.connect() as connection:
                result = await connection.exec_driver_sql("PRAGMA foreign_keys")
                assert result.scalar_one() == 1
                assert database_file.is_file()
        finally:
            await engine.dispose()

    asyncio.run(check_foreign_keys())


def test_database_engine_rejects_invalid_timeout(tmp_path: Path):
    """测试拒绝无效的数据库连接超时时间。"""
    with pytest.raises(ValueError, match="超时时间必须大于 0"):
        create_database_engine(
            database_file=tmp_path / "test.db",
            timeout=0,
        )
