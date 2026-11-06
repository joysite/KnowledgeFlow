"""KnowledgeFlow Alembic 异步数据库迁移环境。"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import URL
from sqlalchemy.engine import Connection

import app.models  # noqa: F401
from app.core.paths import DATABASE_FILE
from app.db.base import Base
from app.db.engine import create_database_engine

# Alembic 配置对象。
config = context.config

# 初始化 Alembic 日志配置。
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 导入全部 ORM 模型后，注册统一元数据。
target_metadata = Base.metadata


def get_database_url() -> URL:
    """获取项目统一管理的 SQLite 异步数据库 URL。"""
    return URL.create(
        drivername="sqlite+aiosqlite",
        database=str(DATABASE_FILE.resolve()),
    )


def run_migrations_offline() -> None:
    """在离线模式下生成迁移 SQL，不建立数据库连接。"""
    url = get_database_url()

    context.configure(
        url=url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """使用同步连接执行 Alembic 迁移操作。"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """通过现有异步数据库引擎执行在线迁移。"""
    connectable = create_database_engine(
        database_file=DATABASE_FILE,
        timeout=30.0,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式入口，使用 asyncio 执行异步数据库迁移。"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
