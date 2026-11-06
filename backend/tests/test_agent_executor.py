"""KnowledgeFlow Agent 执行器测试。"""

import pytest
from pydantic import BaseModel

from app.agent import ToolDefinition, ToolRegistry
from app.agent.executor import (
    AgentError,
    AgentExecutor,
    AgentIterationLimitError,
)
from app.llm import ChatResponse


class ToolArguments(BaseModel):
    """测试工具参数。"""

    value: str


class FakeChatService:
    """按预设顺序返回模型响应。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat_with_tools(self, messages, tools):
        self.calls.append(
            {
                "messages": [message.copy() for message in messages],
                "tools": tools,
            }
        )
        if not self.responses:
            raise AssertionError("模型响应次数超出预期")
        return self.responses.pop(0)


def make_tool_call(name="test_tool", arguments=None):
    """构造 Ollama 工具调用。"""
    return {
        "function": {
            "name": name,
            "arguments": arguments or {"value": "测试"},
        }
    }


def make_registry(handler=None):
    """创建包含测试工具的注册表。"""

    async def default_handler(arguments):
        return {"result": arguments.value}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="test_tool",
            description="测试工具",
            parameters_model=ToolArguments,
            handler=handler or default_handler,
        )
    )
    return registry


@pytest.mark.asyncio
async def test_agent_returns_direct_answer():
    """模型不调用工具时直接返回最终回答。"""
    chat_service = FakeChatService([ChatResponse(content="直接回答", tool_calls=[])])
    executor = AgentExecutor(chat_service, make_registry())

    result = await executor.run("  测试问题  ")

    assert result.answer == "直接回答"
    assert result.tool_calls_count == 0
    assert result.iterations == 0
    assert chat_service.calls[0]["messages"][-1]["content"] == "测试问题"


@pytest.mark.asyncio
async def test_agent_executes_tool_and_returns_final_answer():
    """验证工具执行结果会交回模型。"""
    chat_service = FakeChatService(
        [
            ChatResponse(content="", tool_calls=[make_tool_call()]),
            ChatResponse(content="工具执行后的回答", tool_calls=[]),
        ]
    )
    executor = AgentExecutor(chat_service, make_registry())

    result = await executor.run("调用测试工具")

    assert result.answer == "工具执行后的回答"
    assert result.tool_calls_count == 1
    assert result.iterations == 1

    second_messages = chat_service.calls[1]["messages"]
    assert second_messages[-1]["role"] == "tool"
    assert second_messages[-1]["tool_name"] == "test_tool"
    assert second_messages[-1]["content"] == '{"result":"测试"}'


@pytest.mark.asyncio
async def test_agent_executes_multiple_tool_calls():
    """验证同一轮中的多个工具调用按顺序执行。"""
    chat_service = FakeChatService(
        [
            ChatResponse(
                content="",
                tool_calls=[
                    make_tool_call(arguments={"value": "第一个"}),
                    make_tool_call(arguments={"value": "第二个"}),
                ],
            ),
            ChatResponse(content="两个工具均已执行", tool_calls=[]),
        ]
    )
    executor = AgentExecutor(chat_service, make_registry())

    result = await executor.run("执行两个工具")

    assert result.tool_calls_count == 2
    tool_messages = [
        message for message in chat_service.calls[1]["messages"] if message["role"] == "tool"
    ]
    assert [message["tool_name"] for message in tool_messages] == [
        "test_tool",
        "test_tool",
    ]
    assert [message["content"] for message in tool_messages] == [
        '{"result":"第一个"}',
        '{"result":"第二个"}',
    ]


@pytest.mark.asyncio
async def test_agent_returns_tool_error_to_model():
    """工具不存在时不执行其他工具，并将通用错误交回模型。"""
    chat_service = FakeChatService(
        [
            ChatResponse(
                content="",
                tool_calls=[make_tool_call(name="unknown_tool")],
            ),
            ChatResponse(content="无法使用该工具，已调整回答", tool_calls=[]),
        ]
    )
    executor = AgentExecutor(chat_service, make_registry())

    result = await executor.run("调用不存在的工具")

    assert result.answer == "无法使用该工具，已调整回答"
    assert chat_service.calls[1]["messages"][-1]["content"] == ('{"error":"工具不可用或执行失败"}')


@pytest.mark.asyncio
async def test_agent_stops_after_iteration_limit():
    """连续请求工具调用时达到轮数上限后停止。"""
    chat_service = FakeChatService(
        [
            ChatResponse(content="", tool_calls=[make_tool_call()]),
            ChatResponse(content="", tool_calls=[make_tool_call()]),
        ]
    )
    executor = AgentExecutor(
        chat_service,
        make_registry(),
        max_iterations=1,
    )

    with pytest.raises(AgentIterationLimitError):
        await executor.run("持续调用工具")

    assert len(chat_service.calls) == 2


@pytest.mark.asyncio
async def test_agent_rejects_empty_query():
    """拒绝空问题。"""
    executor = AgentExecutor(
        FakeChatService([]),
        make_registry(),
    )

    with pytest.raises(ValueError, match="用户问题"):
        await executor.run("   ")


@pytest.mark.asyncio
async def test_agent_rejects_empty_registry():
    """未注册工具时拒绝启动执行。"""
    executor = AgentExecutor(
        FakeChatService([]),
        ToolRegistry(),
    )

    with pytest.raises(AgentError, match="未注册"):
        await executor.run("测试")


@pytest.mark.parametrize("max_iterations", [0, -1, True, 1.5])
def test_agent_rejects_invalid_iteration_limit(max_iterations):
    """最大工具调用轮数必须是正整数。"""
    with pytest.raises(ValueError, match="正整数"):
        AgentExecutor(
            FakeChatService([]),
            make_registry(),
            max_iterations=max_iterations,
        )


@pytest.mark.asyncio
async def test_agent_returns_knowledge_rag_answer_without_second_generation():
    """RAG 已生成明确答案时直接返回，避免模型二次改写事实。"""

    async def rag_handler(arguments):
        return {
            "answer": "KnowledgeFlow 使用的向量模型是 nomic-embed-text [2]。",
            "sources": [],
            "retrieved_count": 5,
            "context_token_count": 100,
        }

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="knowledge_rag",
            description="知识库 RAG",
            parameters_model=ToolArguments,
            handler=rag_handler,
        )
    )

    chat_service = FakeChatService(
        [
            ChatResponse(
                content="",
                tool_calls=[make_tool_call(name="knowledge_rag")],
            )
        ]
    )
    executor = AgentExecutor(chat_service, registry)

    result = await executor.run("KnowledgeFlow 使用什么向量模型？")

    assert result.answer == "KnowledgeFlow 使用的向量模型是 nomic-embed-text [2]。"
    assert result.tool_calls_count == 1
    assert result.iterations == 1
    assert len(chat_service.calls) == 1
