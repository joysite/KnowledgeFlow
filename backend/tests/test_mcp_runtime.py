"""KnowledgeFlow MCPRuntime 生命周期测试。"""

import pytest

import app.mcp_server.runtime as runtime_module
from app.mcp_server.runtime import MCPRuntime


class FakeEngine:
    """模拟异步数据库引擎。"""

    def __init__(self):
        self.dispose_called = False

    async def dispose(self):
        self.dispose_called = True


class FakeHTTPClient:
    """模拟 HTTP 客户端。"""

    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


class FakeService:
    """记录共享 HTTP 客户端的模拟服务。"""

    def __init__(self, client):
        self.client = client


class FakeVectorStore:
    """模拟 Chroma 向量存储。"""


def patch_runtime(monkeypatch):
    """替换 MCPRuntime 的外部资源依赖。"""
    engine = FakeEngine()
    client = FakeHTTPClient()

    def session_factory():
        return object()

    created = {"engine": 0, "client": 0, "store": 0}

    def create_engine():
        created["engine"] += 1
        return engine

    def create_client():
        created["client"] += 1
        return client

    def create_store():
        created["store"] += 1
        return FakeVectorStore()

    monkeypatch.setattr(runtime_module, "setup_logging", lambda: None)
    monkeypatch.setattr(runtime_module, "create_database_engine", create_engine)
    monkeypatch.setattr(
        runtime_module,
        "create_session_factory",
        lambda current_engine: session_factory,
    )
    monkeypatch.setattr(
        runtime_module.httpx,
        "AsyncClient",
        create_client,
    )
    monkeypatch.setattr(runtime_module, "EmbeddingService", FakeService)
    monkeypatch.setattr(runtime_module, "OllamaChatService", FakeService)
    monkeypatch.setattr(runtime_module, "ChromaVectorStore", create_store)

    return engine, client, session_factory, created


@pytest.mark.asyncio
async def test_runtime_starts_and_closes_resources(monkeypatch):
    """测试正常启动、共享客户端和资源释放。"""
    engine, client, session_factory, created = patch_runtime(monkeypatch)
    runtime = MCPRuntime()

    await runtime.start()

    assert runtime._started is True
    assert runtime.engine is engine
    assert runtime.session_factory is session_factory
    assert runtime.http_client is client
    assert runtime.embedding_service.client is client
    assert runtime.chat_service.client is client
    assert isinstance(runtime.vector_store, FakeVectorStore)
    assert runtime.create_session() is not None

    await runtime.close()

    assert client.closed is True
    assert engine.dispose_called is True
    assert runtime._started is False

    for name in (
        "engine",
        "session_factory",
        "http_client",
        "embedding_service",
        "chat_service",
        "vector_store",
    ):
        assert getattr(runtime, name) is None

    assert created == {"engine": 1, "client": 1, "store": 1}


@pytest.mark.asyncio
async def test_runtime_start_is_idempotent(monkeypatch):
    """测试重复启动不会重复创建资源。"""
    engine, client, _, created = patch_runtime(monkeypatch)
    runtime = MCPRuntime()

    await runtime.start()
    await runtime.start()

    assert runtime.engine is engine
    assert runtime.http_client is client
    assert created == {"engine": 1, "client": 1, "store": 1}

    await runtime.close()


@pytest.mark.asyncio
async def test_runtime_cleans_resources_when_initialization_fails(monkeypatch):
    """测试初始化失败时释放已经创建的资源。"""
    engine, client, _, created = patch_runtime(monkeypatch)

    def fail_vector_store():
        raise RuntimeError("模拟 Chroma 初始化失败")

    monkeypatch.setattr(
        runtime_module,
        "ChromaVectorStore",
        fail_vector_store,
    )

    runtime = MCPRuntime()

    with pytest.raises(RuntimeError, match="模拟 Chroma 初始化失败"):
        await runtime.start()

    assert client.closed is True
    assert engine.dispose_called is True
    assert runtime._started is False
    assert runtime.engine is None
    assert runtime.http_client is None
    assert runtime.session_factory is None
    assert created == {"engine": 1, "client": 1, "store": 0}


def test_runtime_rejects_session_before_start():
    """测试未启动时不能创建数据库会话。"""
    runtime = MCPRuntime()

    with pytest.raises(RuntimeError, match="尚未启动"):
        runtime.create_session()


@pytest.mark.asyncio
async def test_runtime_close_is_idempotent(monkeypatch):
    """测试重复关闭不会重复释放资源。"""
    engine, client, _, _ = patch_runtime(monkeypatch)
    runtime = MCPRuntime()

    await runtime.start()
    await runtime.close()
    await runtime.close()

    assert client.closed is True
    assert engine.dispose_called is True
