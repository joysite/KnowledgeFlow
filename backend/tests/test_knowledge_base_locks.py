"""KnowledgeFlow 知识库操作锁测试。"""

import asyncio

import pytest

from app.services.knowledge_base_locks import KnowledgeBaseOperationLocks


def test_same_knowledge_base_operations_are_serialized() -> None:
    """同一知识库的操作必须串行执行。"""

    async def run_test() -> None:
        locks = KnowledgeBaseOperationLocks()
        first_acquired = asyncio.Event()
        release_first = asyncio.Event()
        second_acquired = asyncio.Event()

        async def first_operation() -> None:
            async with locks.hold(1):
                first_acquired.set()
                await release_first.wait()

        async def second_operation() -> None:
            await first_acquired.wait()

            async with locks.hold(1):
                second_acquired.set()

        first = asyncio.create_task(first_operation())
        second = asyncio.create_task(second_operation())

        await first_acquired.wait()
        await asyncio.sleep(0)

        assert not second_acquired.is_set()

        release_first.set()
        await asyncio.gather(first, second)

        assert second_acquired.is_set()

    asyncio.run(run_test())


def test_different_knowledge_bases_can_run_concurrently() -> None:
    """不同知识库的操作不应互相阻塞。"""

    async def run_test() -> None:
        locks = KnowledgeBaseOperationLocks()
        first_acquired = asyncio.Event()
        second_acquired = asyncio.Event()

        async def operation(
            knowledge_base_id: int,
            acquired: asyncio.Event,
        ) -> None:
            async with locks.hold(knowledge_base_id):
                acquired.set()
                await asyncio.sleep(0)

        async with locks.hold(1):
            first = asyncio.create_task(operation(1, first_acquired))
            second = asyncio.create_task(operation(2, second_acquired))

            await second_acquired.wait()
            assert not first_acquired.is_set()

        await asyncio.gather(first, second)

        assert first_acquired.is_set()
        assert second_acquired.is_set()

    asyncio.run(run_test())


def test_lock_is_released_after_exception() -> None:
    """操作发生异常后必须释放锁。"""

    async def run_test() -> None:
        locks = KnowledgeBaseOperationLocks()

        with pytest.raises(RuntimeError, match="模拟业务异常"):
            async with locks.hold(1):
                raise RuntimeError("模拟业务异常")

        async with asyncio.timeout(1):
            async with locks.hold(1):
                pass

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "knowledge_base_id",
    [0, -1, True, False, "1", 1.5],
)
def test_invalid_knowledge_base_id_is_rejected(
    knowledge_base_id: object,
) -> None:
    """拒绝非法知识库 ID。"""

    async def run_test() -> None:
        locks = KnowledgeBaseOperationLocks()

        with pytest.raises(ValueError, match="knowledge_base_id"):
            async with locks.hold(knowledge_base_id):
                pass

    asyncio.run(run_test())
