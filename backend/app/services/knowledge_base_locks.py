"""KnowledgeFlow 知识库操作锁管理。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class KnowledgeBaseOperationLocks:
    """按知识库 ID 隔离的异步操作锁管理器。"""

    def __init__(self) -> None:
        """初始化锁集合。"""
        self._locks: dict[int, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, knowledge_base_id: int) -> AsyncIterator[None]:
        """持有指定知识库的操作锁。"""
        if (
            isinstance(knowledge_base_id, bool)
            or not isinstance(knowledge_base_id, int)
            or knowledge_base_id <= 0
        ):
            raise ValueError("knowledge_base_id 必须是正整数")

        async with self._guard:
            lock = self._locks.setdefault(
                knowledge_base_id,
                asyncio.Lock(),
            )

        async with lock:
            yield
