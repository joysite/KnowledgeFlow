"""KnowledgeFlow 数据库应用生命周期测试。"""

from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module


class FakeEngine:
    """用于测试应用生命周期的模拟数据库引擎。"""

    def __init__(self) -> None:
        self.dispose_called = False

    async def dispose(self) -> None:
        """记录数据库引擎释放操作。"""
        self.dispose_called = True


def test_lifespan_initializes_and_disposes_database(
    tmp_path: Path,
    monkeypatch,
):
    """测试应用启动时初始化数据库，关闭时释放引擎。"""
    database_file = tmp_path / "knowledgeflow_test.db"
    engine = FakeEngine()
    session_factory = object()

    monkeypatch.setattr(
        main_module,
        "create_database_engine",
        lambda: engine,
    )
    monkeypatch.setattr(
        main_module,
        "create_session_factory",
        lambda current_engine: session_factory,
    )

    with TestClient(main_module.app) as client:
        # 验证应用启动时创建数据库引擎。
        assert main_module.app.state.database_engine is engine

        # 验证应用启动时创建 Session 工厂。
        assert main_module.app.state.session_factory is session_factory

        # 验证健康检查接口仍然正常。
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    # 验证应用关闭时释放数据库引擎。
    assert engine.dispose_called is True

    # 验证关闭后清理数据库资源引用。
    assert not hasattr(main_module.app.state, "database_engine")
    assert not hasattr(main_module.app.state, "session_factory")

    # 生命周期测试使用模拟引擎，不应创建真实数据库文件。
    assert not database_file.exists()


def test_lifespan_initializes_vector_services(monkeypatch):
    """测试应用启动时初始化向量服务及其依赖关系。"""
    from types import SimpleNamespace

    engine = FakeEngine()
    session_factory = object()

    class FakeAsyncClient:
        def __init__(self):
            self.is_closed = False

        async def aclose(self):
            self.is_closed = True

    created_clients = []

    class RecordingAsyncClient(FakeAsyncClient):
        def __init__(self):
            super().__init__()
            created_clients.append(self)

    class FakeEmbeddingService:
        def __init__(self, client):
            self.client = client

    class FakeVectorStore:
        pass

    class FakeVectorIndexService:
        def __init__(self, embedding_service, vector_store):
            self.embedding_service = embedding_service
            self.vector_store = vector_store

    class FakeChatService:
        """模拟 Ollama 对话服务。"""

        def __init__(self, client):
            self.client = client

    monkeypatch.setattr(main_module, "create_database_engine", lambda: engine)
    monkeypatch.setattr(
        main_module,
        "create_session_factory",
        lambda current_engine: session_factory,
    )
    monkeypatch.setattr(
        main_module,
        "httpx",
        SimpleNamespace(AsyncClient=RecordingAsyncClient),
        raising=False,
    )
    monkeypatch.setattr(
        main_module,
        "EmbeddingService",
        FakeEmbeddingService,
        raising=False,
    )
    monkeypatch.setattr(
        main_module,
        "ChromaVectorStore",
        FakeVectorStore,
        raising=False,
    )
    monkeypatch.setattr(
        main_module,
        "VectorIndexService",
        FakeVectorIndexService,
        raising=False,
    )
    monkeypatch.setattr(
        main_module,
        "OllamaChatService",
        FakeChatService,
        raising=False,
    )

    with TestClient(main_module.app):
        state = main_module.app.state

        assert state.database_engine is engine
        assert state.session_factory is session_factory
        assert state.ollama_client is created_clients[0]
        assert isinstance(state.embedding_service, FakeEmbeddingService)
        assert state.embedding_service.client is created_clients[0]
        assert isinstance(state.vector_store, FakeVectorStore)
        assert isinstance(state.vector_index_service, FakeVectorIndexService)
        assert state.vector_index_service.embedding_service is state.embedding_service
        assert state.vector_index_service.vector_store is state.vector_store
        assert isinstance(state.chat_service, FakeChatService)
        assert state.chat_service.client is created_clients[0]

    assert engine.dispose_called is True
    assert created_clients[0].is_closed is True


def test_lifespan_cleans_resources_when_chroma_initialization_fails(monkeypatch):
    """测试 Chroma 初始化失败时释放已创建的资源。"""
    import pytest

    engine = FakeEngine()
    created_clients = []

    class FakeAsyncClient:
        def __init__(self):
            self.is_closed = False
            created_clients.append(self)

        async def aclose(self):
            self.is_closed = True

    class FakeEmbeddingService:
        def __init__(self, client):
            self.client = client

    def fail_chroma_initialization():
        raise RuntimeError("模拟 Chroma 初始化失败")

    monkeypatch.setattr(main_module, "create_database_engine", lambda: engine)
    monkeypatch.setattr(
        main_module,
        "create_session_factory",
        lambda current_engine: object(),
    )
    monkeypatch.setattr(main_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(main_module, "EmbeddingService", FakeEmbeddingService)
    monkeypatch.setattr(
        main_module,
        "ChromaVectorStore",
        fail_chroma_initialization,
    )

    with pytest.raises(RuntimeError, match="模拟 Chroma 初始化失败"):
        with TestClient(main_module.app):
            pass

    assert len(created_clients) == 1
    assert created_clients[0].is_closed is True
    assert engine.dispose_called is True

    for name in (
        "database_engine",
        "session_factory",
        "ollama_client",
        "embedding_service",
        "vector_store",
        "vector_index_service",
        "chat_service",
    ):
        assert not hasattr(main_module.app.state, name)
