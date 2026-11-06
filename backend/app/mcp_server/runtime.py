"""KnowledgeFlow MCP Server 资源生命周期管理。"""

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.logging import setup_logging
from app.db.engine import create_database_engine
from app.db.session import create_session_factory
from app.embeddings import EmbeddingService
from app.llm import OllamaChatService
from app.vectorstore import ChromaVectorStore


class MCPRuntime:
    """管理 MCP Server 使用的共享基础资源。"""

    def __init__(self) -> None:
        """初始化资源引用。"""
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        self.http_client: httpx.AsyncClient | None = None
        self.embedding_service: EmbeddingService | None = None
        self.chat_service: OllamaChatService | None = None
        self.vector_store: ChromaVectorStore | None = None
        self._started = False

    async def start(self) -> None:
        """初始化 MCP Server 所需资源。"""
        if self._started:
            return

        try:
            setup_logging()

            self.engine = create_database_engine()
            self.session_factory = create_session_factory(self.engine)

            self.http_client = httpx.AsyncClient()
            self.embedding_service = EmbeddingService(client=self.http_client)
            self.chat_service = OllamaChatService(client=self.http_client)

            self.vector_store = ChromaVectorStore()

            self._started = True
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        """释放 MCP Server 资源。"""
        self._started = False

        try:
            if self.http_client is not None:
                await self.http_client.aclose()
        finally:
            self.http_client = None
            self.embedding_service = None
            self.chat_service = None
            self.vector_store = None

            try:
                if self.engine is not None:
                    await self.engine.dispose()
            finally:
                self.engine = None
                self.session_factory = None

    def create_session(self) -> AsyncSession:
        """创建独立的数据库会话。"""
        if not self._started or self.session_factory is None:
            raise RuntimeError("MCPRuntime 尚未启动")

        return self.session_factory()
