"""KnowledgeFlow 异步数据库引擎管理模块。"""

from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.paths import DATABASE_FILE


def _enable_sqlite_foreign_keys(
    dbapi_connection: Any,
    connection_record: Any,
) -> None:
    """启用 SQLite 外键约束。"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_database_engine(
    database_file: Path = DATABASE_FILE,
    echo: bool = False,
    timeout: float = 30.0,
) -> AsyncEngine:
    """
    创建 SQLAlchemy 异步数据库引擎。

    Args:
        database_file: SQLite 数据库文件路径。
        echo: 是否输出 SQL 执行日志。
        timeout: SQLite 等待数据库锁释放的超时时间，单位为秒。

    Returns:
        SQLAlchemy 异步数据库引擎。
    """
    database_file = Path(database_file).expanduser().resolve()

    if timeout <= 0:
        raise ValueError("数据库连接超时时间必须大于 0")

    # 确保数据库父目录存在。
    database_file.parent.mkdir(parents=True, exist_ok=True)

    database_url = URL.create(
        drivername="sqlite+aiosqlite",
        database=str(database_file),
    )

    engine = create_async_engine(
        database_url,
        echo=echo,
        connect_args={"timeout": timeout},
        pool_pre_ping=True,
    )

    # 每次建立新连接时启用 SQLite 外键约束。
    event.listen(
        engine.sync_engine,
        "connect",
        _enable_sqlite_foreign_keys,
    )

    return engine
