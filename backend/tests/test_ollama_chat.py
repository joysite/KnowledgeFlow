"""Ollama Chat 服务测试。"""

import httpx
import pytest

from app.core.config import Settings
from app.llm import ChatError, OllamaChatService


@pytest.fixture
def settings() -> Settings:
    """提供测试配置。"""
    return Settings(
        ollama_base_url="http://ollama.test",
        chat_model="qwen2.5-coder:7b",
        chat_timeout_seconds=30,
    )


@pytest.mark.asyncio
async def test_chat_success(settings: Settings):
    """测试正常生成对话内容。"""

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.read())
        assert request.url.path == "/api/chat"
        assert body["model"] == "qwen2.5-coder:7b"
        assert body["stream"] is False
        assert body["messages"][0]["role"] == "user"
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "RAG 是检索增强生成。"}},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = OllamaChatService(client, settings)
        result = await service.chat([{"role": "user", "content": "什么是 RAG？"}])

    assert result == "RAG 是检索增强生成。"


@pytest.mark.asyncio
async def test_chat_handles_http_error(settings: Settings):
    """测试 HTTP 错误处理。"""
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    async with httpx.AsyncClient(transport=transport) as client:
        service = OllamaChatService(client, settings)

        with pytest.raises(ChatError, match="请求 Ollama"):
            await service.chat([{"role": "user", "content": "测试"}])


@pytest.mark.asyncio
async def test_chat_handles_invalid_json(settings: Settings):
    """测试无效 JSON 响应处理。"""
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"invalid-json"))
    async with httpx.AsyncClient(transport=transport) as client:
        service = OllamaChatService(client, settings)

        with pytest.raises(ChatError, match="无效 JSON"):
            await service.chat([{"role": "user", "content": "测试"}])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"message": None},
        {"message": {}},
        {"message": {"content": None}},
        {"message": {"content": ""}},
        {"message": {"content": "   "}},
        {"error": "model not found"},
    ],
)
async def test_chat_rejects_invalid_response(settings: Settings, payload):
    """测试异常响应结构处理。"""
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        service = OllamaChatService(client, settings)

        with pytest.raises(ChatError):
            await service.chat([{"role": "user", "content": "测试"}])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "messages",
    [
        [],
        None,
        [{"role": "invalid", "content": "测试"}],
        [{"role": "user", "content": ""}],
        [{"role": "user", "content": "   "}],
        [{"role": "user", "content": None}],
        ["invalid"],
    ],
)
async def test_chat_rejects_invalid_messages(settings: Settings, messages):
    """测试非法输入在请求前被拒绝。"""
    async with httpx.AsyncClient() as client:
        service = OllamaChatService(client, settings)

        with pytest.raises(ValueError):
            await service.chat(messages)
