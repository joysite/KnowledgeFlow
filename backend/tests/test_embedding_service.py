"""Ollama Embedding 服务测试。"""

import httpx
import pytest

from app.core.config import Settings
from app.embeddings import EmbeddingError, EmbeddingService


@pytest.fixture
def settings() -> Settings:
    """提供测试配置。"""
    return Settings(
        ollama_base_url="http://ollama.test",
        embedding_model="nomic-embed-text:latest",
    )


@pytest.mark.asyncio
async def test_embed_text_success(settings: Settings) -> None:
    """验证正常生成文本向量。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        assert request.read()
        return httpx.Response(
            200,
            json={"embeddings": [[0.1, 0.2, 0.3]]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = EmbeddingService(client, settings)
        result = await service.embed_text("KnowledgeFlow")

    assert result == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_embed_text_rejects_empty_text(
    settings: Settings,
) -> None:
    """验证空文本在请求前被拒绝。"""
    async with httpx.AsyncClient() as client:
        service = EmbeddingService(client, settings)

        with pytest.raises(ValueError, match="文本不能为空"):
            await service.embed_text("   ")


@pytest.mark.asyncio
async def test_embed_text_handles_http_error(
    settings: Settings,
) -> None:
    """验证 HTTP 错误被转换为 EmbeddingError。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = EmbeddingService(client, settings)

        with pytest.raises(EmbeddingError, match="请求 Ollama"):
            await service.embed_text("测试文本")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"embeddings": []},
        {"embeddings": [[0.1], [0.2]]},
        {"embeddings": [[]]},
        {"embeddings": [[0.1, "invalid"]]},
        {"embeddings": [[float("nan")]]},
        {"embeddings": [[float("inf")]]},
        {"embeddings": [None]},
    ],
)
async def test_embed_text_rejects_invalid_response(
    settings: Settings,
    payload: dict,
) -> None:
    """验证无效的向量响应被拒绝。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = EmbeddingService(client, settings)

        with pytest.raises(EmbeddingError):
            await service.embed_text("测试文本")


@pytest.mark.asyncio
async def test_embed_text_handles_invalid_json(
    settings: Settings,
) -> None:
    """验证无效 JSON 响应被拒绝。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"invalid-json")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = EmbeddingService(client, settings)

        with pytest.raises(EmbeddingError, match="无效 JSON"):
            await service.embed_text("测试文本")


@pytest.mark.asyncio
async def test_embed_texts_success(settings: Settings) -> None:
    """验证批量生成向量。"""

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.read())
        assert body["input"] == ["第一条文本", "第二条文本"]
        return httpx.Response(
            200,
            json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = EmbeddingService(client, settings)
        result = await service.embed_texts(["第一条文本", "第二条文本"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]


@pytest.mark.asyncio
async def test_embed_texts_rejects_empty_input(settings: Settings) -> None:
    """验证空批次和空文本被拒绝。"""
    async with httpx.AsyncClient() as client:
        service = EmbeddingService(client, settings)

        with pytest.raises(ValueError):
            await service.embed_texts([])

        with pytest.raises(ValueError):
            await service.embed_texts(["正常文本", " "])


@pytest.mark.asyncio
async def test_embed_texts_rejects_dimension_mismatch(
    settings: Settings,
) -> None:
    """验证批量向量维度不一致时抛出异常。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"embeddings": [[0.1, 0.2], [0.3]]},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = EmbeddingService(client, settings)

        with pytest.raises(EmbeddingError, match="维度不一致"):
            await service.embed_texts(["第一条", "第二条"])
