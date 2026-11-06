"""基于 Ollama 的文本 Embedding 服务。"""

import math

import httpx

from app.core.config import Settings, get_settings


class EmbeddingError(RuntimeError):
    """Embedding 请求或响应异常。"""


class EmbeddingService:
    """调用 Ollama API 生成文本向量。"""

    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings | None = None,
    ) -> None:
        """初始化服务，HTTP 客户端的生命周期由调用方管理。"""
        self.client = client
        self.settings = settings or get_settings()
        self.endpoint = f"{self.settings.ollama_base_url.rstrip('/')}/api/embed"

    async def _request_embeddings(self, texts: list[str]) -> list[list[float]]:
        """请求 Ollama 并解析批量向量响应。"""
        try:
            response = await self.client.post(
                self.endpoint,
                json={
                    "model": self.settings.embedding_model,
                    "input": texts,
                },
                timeout=self.settings.embedding_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise EmbeddingError("请求 Ollama Embedding 服务失败") from exc
        except ValueError as exc:
            raise EmbeddingError("Ollama 返回了无效 JSON") from exc

        embeddings = payload.get("embeddings") if isinstance(payload, dict) else None
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise EmbeddingError("Ollama 返回的 Embedding 数量不正确")

        results = []
        dimension = None

        for vector in embeddings:
            if not isinstance(vector, list) or not vector:
                raise EmbeddingError("Ollama 返回了空 Embedding")

            if dimension is None:
                dimension = len(vector)
            elif len(vector) != dimension:
                raise EmbeddingError("Embedding 向量维度不一致")

            result = []
            for value in vector:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise EmbeddingError("Embedding 包含非数值元素")
                if not math.isfinite(value):
                    raise EmbeddingError("Embedding 包含非有限数值")
                result.append(float(value))

            results.append(result)

        return results

    async def embed_text(self, text: str) -> list[float]:
        """将单条文本转换为 Embedding 向量。"""
        if not isinstance(text, str) or not text.strip():
            raise ValueError("待向量化文本不能为空")

        embeddings = await self._request_embeddings([text])
        return embeddings[0]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量将文本转换为 Embedding 向量。"""
        if not isinstance(texts, list) or not texts:
            raise ValueError("待向量化文本列表不能为空")

        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("文本列表中不能包含空文本")

        return await self._request_embeddings(texts)
