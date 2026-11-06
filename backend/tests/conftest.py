"""KnowledgeFlow 测试公共 Fixture。"""

import asyncio
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.db.engine import create_database_engine
from app.db.session import create_session_factory


@pytest.fixture
def database(
    tmp_path: Path,
) -> Generator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]], None, None]:
    """创建独立的临时 SQLite 数据库和 Session 工厂。"""
    engine = create_database_engine(tmp_path / "test.db")
    session_factory = create_session_factory(engine)

    async def create_tables() -> None:
        """创建测试所需的数据表。"""
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    try:
        asyncio.run(create_tables())
        yield engine, session_factory
    finally:
        asyncio.run(engine.dispose())
