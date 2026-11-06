"""KnowledgeFlow Agent 工具注册与调用测试。"""

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.agent import (
    ToolArgumentError,
    ToolDefinition,
    ToolExecutionError,
    ToolNotFoundError,
    ToolRegistry,
)


class SearchArguments(BaseModel):
    """模拟知识检索工具参数。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


async def fake_search(arguments: SearchArguments) -> dict:
    """模拟异步检索工具。"""
    return {"query": arguments.query, "top_k": arguments.top_k}


def create_tool(handler=fake_search) -> ToolDefinition:
    """创建测试工具定义。"""
    return ToolDefinition(
        name="knowledge_search",
        description="检索知识库内容",
        parameters_model=SearchArguments,
        handler=handler,
    )


def test_register_and_get_tool():
    registry = ToolRegistry()
    tool = create_tool()
    registry.register(tool)

    assert registry.get("knowledge_search") is tool
    assert registry.list_tools() == [tool]


def test_register_rejects_duplicate_name():
    registry = ToolRegistry()
    registry.register(create_tool())

    with pytest.raises(ValueError, match="工具已注册"):
        registry.register(create_tool())


@pytest.mark.parametrize(
    "name",
    ["", "123search", "knowledge-search", "knowledge search", "a" * 65],
)
def test_tool_definition_rejects_invalid_name(name):
    with pytest.raises(ValueError, match="工具名称"):
        ToolDefinition(
            name=name,
            description="测试工具",
            parameters_model=SearchArguments,
            handler=fake_search,
        )


def test_tool_definition_rejects_invalid_description():
    with pytest.raises(ValueError, match="工具描述"):
        ToolDefinition(
            name="test_tool",
            description="  ",
            parameters_model=SearchArguments,
            handler=fake_search,
        )


def test_tool_definition_rejects_invalid_parameter_model():
    with pytest.raises(TypeError, match="Pydantic"):
        ToolDefinition(
            name="test_tool",
            description="测试工具",
            parameters_model=dict,
            handler=fake_search,
        )


def test_tool_definition_rejects_sync_handler():
    def sync_handler(arguments):
        return arguments

    with pytest.raises(TypeError, match="异步函数"):
        create_tool(handler=sync_handler)


def test_register_rejects_non_definition():
    registry = ToolRegistry()

    with pytest.raises(TypeError, match="ToolDefinition"):
        registry.register(object())


def test_get_rejects_unknown_tool():
    registry = ToolRegistry()

    with pytest.raises(ToolNotFoundError, match="工具未注册"):
        registry.get("unknown_tool")


def test_export_ollama_tool_schema():
    registry = ToolRegistry()
    registry.register(create_tool())

    tools = registry.to_ollama_tools()

    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "knowledge_search"

    schema = tools[0]["function"]["parameters"]
    assert schema["properties"]["query"]["type"] == "string"
    assert schema["properties"]["top_k"]["type"] == "integer"
    assert "query" in schema["required"]


@pytest.mark.asyncio
async def test_call_validates_and_executes_tool():
    registry = ToolRegistry()
    registry.register(create_tool())

    result = await registry.call(
        "knowledge_search",
        {"query": "混合检索", "top_k": 3},
    )

    assert result == {"query": "混合检索", "top_k": 3}


@pytest.mark.asyncio
async def test_call_uses_parameter_defaults():
    registry = ToolRegistry()
    registry.register(create_tool())

    result = await registry.call("knowledge_search", {"query": "RAG"})

    assert result["top_k"] == 5


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        "invalid",
        None,
        {"query": ""},
        {"query": "测试", "top_k": 0},
        {"query": "测试", "top_k": 21},
        {"query": "测试", "unexpected": True},
    ],
)
@pytest.mark.asyncio
async def test_call_rejects_invalid_arguments(arguments):
    registry = ToolRegistry()
    registry.register(create_tool())

    with pytest.raises(ToolArgumentError):
        await registry.call("knowledge_search", arguments)


@pytest.mark.asyncio
async def test_call_rejects_unregistered_tool():
    registry = ToolRegistry()

    with pytest.raises(ToolNotFoundError):
        await registry.call("unknown_tool", {})


@pytest.mark.asyncio
async def test_call_wraps_handler_error():
    async def failing_handler(arguments):
        raise RuntimeError("内部执行细节")

    registry = ToolRegistry()
    registry.register(create_tool(handler=failing_handler))

    with pytest.raises(ToolExecutionError, match="工具执行失败") as exc_info:
        await registry.call("knowledge_search", {"query": "测试"})

    assert isinstance(exc_info.value.__cause__, RuntimeError)
