"""Ollama Function Calling 测试。"""

import httpx
import pytest

from app.core.config import Settings
from app.llm import ChatError, OllamaChatService


@pytest.fixture
def settings():
    return Settings(
        ollama_base_url="http://ollama.test",
        chat_model="qwen2.5-coder:7b",
        chat_timeout_seconds=30,
    )


@pytest.fixture
def tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "knowledge_rag",
                "description": "检索知识库",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "knowledge_base_id": {"type": "integer"},
                    },
                    "required": ["query", "knowledge_base_id"],
                },
            },
        }
    ]


@pytest.mark.asyncio
async def test_chat_with_tools_success(settings, tools):
    """验证模型返回工具调用及请求参数。"""
    expected_call = {
        "function": {
            "name": "knowledge_rag",
            "arguments": {
                "query": "什么是 RAG？",
                "knowledge_base_id": 1,
            },
        }
    }

    def handler(request):
        import json

        body = json.loads(request.read())
        assert body["model"] == "qwen2.5-coder:7b"
        assert body["stream"] is False
        assert body["tools"] == tools
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [expected_call],
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = OllamaChatService(client, settings)
        result = await service.chat_with_tools(
            [{"role": "user", "content": "什么是 RAG？"}],
            tools,
        )

    assert result.content == ""
    assert result.tool_calls == [expected_call]


@pytest.mark.asyncio
async def test_chat_with_tools_returns_text(settings, tools):
    """验证模型可以直接返回普通文本。"""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "这是普通回答。",
                }
            },
        )
    )

    async with httpx.AsyncClient(transport=transport) as client:
        service = OllamaChatService(client, settings)
        result = await service.chat_with_tools(
            [{"role": "user", "content": "你好"}],
            tools,
        )

    assert result.content == "这是普通回答。"
    assert result.tool_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_calls",
    [
        [None],
        [{}],
        [{"function": None}],
        [{"function": {"name": "", "arguments": {}}}],
        [{"function": {"name": "knowledge_rag", "arguments": []}}],
    ],
)
async def test_chat_with_tools_rejects_invalid_tool_calls(settings, tools, tool_calls):
    """验证异常工具调用结构被拒绝。"""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": tool_calls,
                }
            },
        )
    )

    async with httpx.AsyncClient(transport=transport) as client:
        service = OllamaChatService(client, settings)

        with pytest.raises(ChatError):
            await service.chat_with_tools(
                [{"role": "user", "content": "测试"}],
                tools,
            )


@pytest.mark.asyncio
async def test_chat_with_tools_rejects_empty_response(settings, tools):
    """验证没有文本和工具调用的响应被拒绝。"""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [],
                }
            },
        )
    )

    async with httpx.AsyncClient(transport=transport) as client:
        service = OllamaChatService(client, settings)

        with pytest.raises(ChatError, match="未返回"):
            await service.chat_with_tools(
                [{"role": "user", "content": "测试"}],
                tools,
            )


@pytest.mark.asyncio
async def test_chat_with_tools_rejects_empty_tools(settings):
    """验证空工具定义在请求前被拒绝。"""
    async with httpx.AsyncClient() as client:
        service = OllamaChatService(client, settings)

        with pytest.raises(ValueError, match="工具定义列表"):
            await service.chat_with_tools(
                [{"role": "user", "content": "测试"}],
                [],
            )


@pytest.mark.asyncio
async def test_chat_with_tools_handles_http_error(settings, tools):
    """验证工具调用请求的 HTTP 错误处理。"""
    transport = httpx.MockTransport(lambda request: httpx.Response(500))

    async with httpx.AsyncClient(transport=transport) as client:
        service = OllamaChatService(client, settings)

        with pytest.raises(ChatError, match="请求 Ollama"):
            await service.chat_with_tools(
                [{"role": "user", "content": "测试"}],
                tools,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        '{"name":"knowledge_rag","arguments":{"query":"RAG","knowledge_base_id":1}}',
        '<tool_call>{"name":"knowledge_rag","arguments":{"query":"RAG","knowledge_base_id":1}}</tool_call>',
    ],
)
async def test_chat_with_tools_parses_qwen_json_call(settings, tools, content):
    """验证兼容解析 Qwen 返回的裸 JSON 和 tool_call 标签。"""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": content,
                }
            },
        )
    )

    async with httpx.AsyncClient(transport=transport) as client:
        service = OllamaChatService(client, settings)
        result = await service.chat_with_tools(
            [{"role": "user", "content": "查询 RAG"}],
            tools,
        )

    assert result.content == ""
    assert result.tool_calls[0]["function"]["name"] == "knowledge_rag"
    assert result.tool_calls[0]["function"]["arguments"]["query"] == "RAG"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        '{"name":"unknown_tool","arguments":{}}',
        '{"name":"knowledge_rag","arguments":[]}',
        '{"name":"knowledge_rag","arguments":{},"extra":"value"}',
        '请调用工具 {"name":"knowledge_rag","arguments":{}}',
        '{"name":',
    ],
)
async def test_chat_with_tools_rejects_unsafe_compat_content(settings, tools, content):
    """验证未知工具、非法参数及混杂文本不会被解析执行。"""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": content,
                }
            },
        )
    )

    async with httpx.AsyncClient(transport=transport) as client:
        service = OllamaChatService(client, settings)
        result = await service.chat_with_tools(
            [{"role": "user", "content": "测试"}],
            tools,
        )

    assert result.tool_calls == []
    assert result.content == content.strip()


@pytest.mark.asyncio
async def test_native_tool_calls_take_priority_over_content(settings, tools):
    """验证原生工具调用优先于兼容解析。"""
    native_call = {
        "function": {
            "name": "knowledge_rag",
            "arguments": {"query": "native", "knowledge_base_id": 1},
        }
    }
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"name":"knowledge_rag","arguments":{"query":"fallback"}}',
                    "tool_calls": [native_call],
                }
            },
        )
    )

    async with httpx.AsyncClient(transport=transport) as client:
        service = OllamaChatService(client, settings)
        result = await service.chat_with_tools(
            [{"role": "user", "content": "测试"}],
            tools,
        )

    assert result.tool_calls == [native_call]
