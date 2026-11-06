"""基于 Ollama 的对话生成服务。"""

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings


class ChatError(RuntimeError):
    """Ollama 对话请求或响应异常。"""


@dataclass(frozen=True, slots=True)
class ChatResponse:
    """Ollama 对话响应。"""

    content: str
    tool_calls: list[dict[str, Any]]


class OllamaChatService:
    """调用 Ollama Chat API 生成文本或工具调用。"""

    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings | None = None,
    ) -> None:
        """初始化服务，HTTP 客户端生命周期由调用方管理。"""
        self.client = client
        self.settings = settings or get_settings()
        self.endpoint = f"{self.settings.ollama_base_url.rstrip('/')}/api/chat"

    @staticmethod
    def _validate_messages(messages: list[dict[str, Any]]) -> None:
        """校验对话消息。"""
        if not isinstance(messages, list) or not messages:
            raise ValueError("对话消息列表不能为空")

        allowed_roles = {"system", "user", "assistant", "tool"}

        for message in messages:
            if not isinstance(message, dict):
                raise ValueError("对话消息格式不正确")

            if message.get("role") not in allowed_roles:
                raise ValueError("对话消息角色不合法")

            content = message.get("content", "")

            if not isinstance(content, str):
                raise ValueError("对话消息内容必须是字符串")

            if message["role"] != "assistant" and not content.strip():
                raise ValueError("对话消息内容不能为空")

    async def _request(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """发送 Ollama 请求并校验响应结构。"""
        payload: dict[str, Any] = {
            "model": self.settings.chat_model,
            "messages": messages,
            "stream": False,
        }

        if tools is not None:
            payload["tools"] = tools

        try:
            response = await self.client.post(
                self.endpoint,
                json=payload,
                timeout=self.settings.chat_timeout_seconds,
            )
            response.raise_for_status()
            result = response.json()
        except httpx.HTTPError as exc:
            raise ChatError("请求 Ollama Chat 服务失败") from exc
        except ValueError as exc:
            raise ChatError("Ollama 返回了无效 JSON") from exc

        if not isinstance(result, dict):
            raise ChatError("Ollama 返回的数据格式不正确")

        if result.get("error"):
            raise ChatError("Ollama 对话生成失败")

        message = result.get("message")

        if not isinstance(message, dict):
            raise ChatError("Ollama 返回的消息结构不正确")

        if message.get("role") != "assistant":
            raise ChatError("Ollama 返回的消息角色不正确")

        return message

    async def chat(self, messages: list[dict[str, Any]]) -> str:
        """发送普通对话并返回模型生成的文本。"""
        self._validate_messages(messages)

        message = await self._request(messages)
        content = message.get("content")

        if not isinstance(content, str) or not content.strip():
            raise ChatError("Ollama 返回的对话内容为空或格式不正确")

        if message.get("tool_calls"):
            raise ChatError("普通对话接口不支持工具调用响应")

        return content.strip()

    @staticmethod
    def _parse_compat_tool_call(
        content: str,
        tools: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """兼容解析模型未被 Ollama 识别的完整 JSON 工具调用。"""
        text = content.strip()

        if text.startswith("<tool_call>") and text.endswith("</tool_call>"):
            text = text[len("<tool_call>") : -len("</tool_call>")].strip()

        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return []

        if not isinstance(payload, dict):
            return []

        if set(payload) != {"name", "arguments"}:
            return []

        name = payload["name"]
        arguments = payload["arguments"]

        if not isinstance(name, str) or not isinstance(arguments, dict):
            return []

        allowed_names = {
            item.get("function", {}).get("name")
            for item in tools
            if isinstance(item, dict) and isinstance(item.get("function"), dict)
        }

        if name not in allowed_names:
            return []

        return [{"function": {"name": name, "arguments": arguments}}]

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatResponse:
        """发送支持工具调用的对话请求。"""
        self._validate_messages(messages)

        if not isinstance(tools, list) or not tools:
            raise ValueError("工具定义列表不能为空")

        message = await self._request(messages, tools)

        content = message.get("content", "")
        tool_calls = message.get("tool_calls", [])

        if not isinstance(content, str):
            raise ChatError("Ollama 返回的对话内容格式不正确")

        if not isinstance(tool_calls, list):
            raise ChatError("Ollama 返回的工具调用格式不正确")

        # 原生工具调用优先；仅在原生结果为空时启用兼容解析。
        if not tool_calls and content.strip():
            tool_calls = self._parse_compat_tool_call(content, tools)
            if tool_calls:
                content = ""

        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                raise ChatError("Ollama 返回了无效的工具调用")

            function = tool_call.get("function")

            if not isinstance(function, dict):
                raise ChatError("Ollama 返回的工具函数结构不正确")

            name = function.get("name")
            arguments = function.get("arguments")

            if not isinstance(name, str) or not name:
                raise ChatError("Ollama 返回的工具名称无效")

            if not isinstance(arguments, dict):
                raise ChatError("Ollama 返回的工具参数无效")

        if not content.strip() and not tool_calls:
            raise ChatError("Ollama 未返回文本或工具调用")

        return ChatResponse(
            content=content.strip(),
            tool_calls=tool_calls,
        )
