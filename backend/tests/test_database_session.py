"""KnowledgeFlow 异步数据库会话测试。"""

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import create_database_engine
from app.db.session import create_session_factory, get_db_session


def create_test_request(session_factory):
    """创建携带数据库会话工厂的测试请求。"""
    app = FastAPI()
    app.state.session_factory = session_factory

    from starlette.requests import Request

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/test",
        "raw_path": b"/test",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
        "app": app,
    }

    return Request(scope)


def test_create_session_factory(tmp_path: Path):
    """测试创建异步 Session 工厂。"""
    engine = create_database_engine(tmp_path / "test.db")
    factory = create_session_factory(engine)

    try:
        assert factory.kw["bind"] is engine
        assert factory.kw["autoflush"] is False
        assert factory.kw["expire_on_commit"] is False
        assert factory.class_ is AsyncSession
    finally:
        asyncio.run(engine.dispose())


def test_get_db_session_returns_async_session(tmp_path: Path):
    """测试请求依赖能够获取异步 Session。"""
    engine = create_database_engine(tmp_path / "test.db")
    factory = create_session_factory(engine)
    request = create_test_request(factory)

    async def run_test():
        generator = get_db_session(request)

        try:
            session = await anext(generator)

            assert isinstance(session, AsyncSession)
            assert session.bind is engine
        finally:
            await generator.aclose()
            await engine.dispose()

    asyncio.run(run_test())


def test_get_db_session_rolls_back_on_exception(tmp_path: Path):
    """测试请求发生异常时自动回滚事务。"""
    engine = create_database_engine(tmp_path / "test.db")
    factory = create_session_factory(engine)
    request = create_test_request(factory)

    async def run_test():
        async with engine.begin() as connection:
            await connection.execute(
                text("CREATE TABLE test_records (id INTEGER PRIMARY KEY, name TEXT)")
            )

        generator = get_db_session(request)
        session = await anext(generator)

        try:
            await session.execute(text("INSERT INTO test_records (name) VALUES ('rollback-test')"))

            with pytest.raises(RuntimeError, match="模拟业务异常"):
                await generator.athrow(RuntimeError("模拟业务异常"))

            async with factory() as check_session:
                result = await check_session.execute(text("SELECT COUNT(*) FROM test_records"))

                assert result.scalar_one() == 0
        finally:
            await engine.dispose()

    asyncio.run(run_test())


def test_get_db_session_requires_initialized_factory():
    """测试未初始化 Session 工厂时返回明确异常。"""
    request = create_test_request(None)

    async def run_test():
        generator = get_db_session(request)

        with pytest.raises(
            RuntimeError,
            match="数据库会话工厂尚未初始化",
        ):
            await anext(generator)

    asyncio.run(run_test())


def test_get_db_session_closes_and_rolls_back_on_exit(
    tmp_path: Path,
):
    """测试请求结束时关闭会话并回滚未提交事务。"""
    engine = create_database_engine(tmp_path / "test.db")
    factory = create_session_factory(engine)
    request = create_test_request(factory)

    async def run_test():
        async with engine.begin() as connection:
            await connection.execute(
                text("CREATE TABLE test_records (id INTEGER PRIMARY KEY, name TEXT)")
            )

        generator = get_db_session(request)
        session = await anext(generator)

        await session.execute(text("INSERT INTO test_records (name) VALUES ('uncommitted-test')"))

        await generator.aclose()

        async with factory() as check_session:
            result = await check_session.execute(text("SELECT COUNT(*) FROM test_records"))

            assert result.scalar_one() == 0

        await engine.dispose()

    asyncio.run(run_test())
