"""KnowledgeFlow 异步数据库会话管理模块。"""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """
    创建异步数据库会话工厂。

    Args:
        engine: SQLAlchemy 异步数据库引擎。

    Returns:
        异步数据库会话工厂。
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autoflush=False,
        expire_on_commit=False,
    )


async def get_db_session(
    request: Request,
) -> AsyncIterator[AsyncSession]:
    """
    获取当前请求使用的数据库会话。

    从 FastAPI 应用状态中获取 Session 工厂，
    为当前请求创建独立的数据库会话。

    Args:
        request: 当前 FastAPI 请求对象。

    Yields:
        当前请求使用的异步数据库会话。

    Raises:
        RuntimeError: 应用尚未配置数据库会话工厂。
    """
    session_factory = getattr(
        request.app.state,
        "session_factory",
        None,
    )

    if session_factory is None:
        raise RuntimeError("数据库会话工厂尚未初始化，请检查应用 lifespan 配置")

    async with session_factory() as session:
        try:
            yield session
        except BaseException:
            # 请求执行异常时回滚未提交的事务。
            await session.rollback()
            raise
