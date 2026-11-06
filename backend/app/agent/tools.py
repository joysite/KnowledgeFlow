"""KnowledgeFlow Agent 工具定义与注册。"""

import inspect
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

ToolHandler = Callable[[BaseModel], Awaitable[Any]]
TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")


class ToolNotFoundError(LookupError):
    """请求的工具未注册。"""


class ToolArgumentError(ValueError):
    """工具参数不符合定义。"""


class ToolExecutionError(RuntimeError):
    """工具处理函数执行失败。"""


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """描述一个可供 Agent 调用的工具。"""

    name: str
    description: str
    parameters_model: type[BaseModel]
    handler: ToolHandler

    def __post_init__(self) -> None:
        """校验工具定义。"""
        if not isinstance(self.name, str) or not TOOL_NAME_PATTERN.fullmatch(self.name):
            raise ValueError("工具名称格式不合法")

        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("工具描述不能为空")

        if not (
            isinstance(self.parameters_model, type) and issubclass(self.parameters_model, BaseModel)
        ):
            raise TypeError("工具参数必须使用 Pydantic BaseModel 定义")

        if not callable(self.handler) or not inspect.iscoroutinefunction(self.handler):
            raise TypeError("工具处理函数必须是异步函数")


class ToolRegistry:
    """管理已授权工具并负责参数校验和调用。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """注册工具，拒绝重复名称。"""
        if not isinstance(tool, ToolDefinition):
            raise TypeError("只能注册 ToolDefinition 实例")

        if tool.name in self._tools:
            raise ValueError(f"工具已注册：{tool.name}")

        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        """获取已注册工具。"""
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"工具未注册：{name}") from exc

    def list_tools(self) -> list[ToolDefinition]:
        """按注册顺序返回工具列表。"""
        return list(self._tools.values())

    def to_ollama_tools(self) -> list[dict[str, Any]]:
        """导出 Ollama Function Calling 工具定义。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters_model.model_json_schema(),
                },
            }
            for tool in self._tools.values()
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        """校验参数并调用已注册工具。"""
        tool = self.get(name)

        if not isinstance(arguments, dict):
            raise ToolArgumentError("工具参数必须是 JSON 对象")

        try:
            validated_arguments = tool.parameters_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolArgumentError("工具参数校验失败") from exc

        try:
            return await tool.handler(validated_arguments)
        except Exception as exc:
            raise ToolExecutionError(f"工具执行失败：{name}") from exc
