"""KnowledgeFlow RAG Agent 工具适配器。"""

from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agent.tools import ToolDefinition
from app.services.rag import RAGService


class RAGToolArguments(BaseModel):
    """独立调用 RAG 工具时使用的参数。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=10000)
    knowledge_base_id: int = Field(strict=True, gt=0)
    top_k: int = Field(default=5, strict=True, gt=0, le=100)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("查询文本不能为空")
        return value


class BoundRAGToolArguments(BaseModel):
    """已绑定知识库的 Agent 工具参数。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=10000)
    top_k: int = Field(default=5, strict=True, gt=0, le=100)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("查询文本不能为空")
        return value


def create_rag_tool(
    rag_service: RAGService,
    knowledge_base_id: int | None = None,
) -> ToolDefinition:
    """创建 RAG 工具，可选绑定固定知识库。"""

    if knowledge_base_id is not None:
        if (
            isinstance(knowledge_base_id, bool)
            or not isinstance(knowledge_base_id, int)
            or knowledge_base_id <= 0
        ):
            raise ValueError("knowledge_base_id 必须是正整数")

        async def bound_handler(arguments: BoundRAGToolArguments) -> dict[str, Any]:
            result = await rag_service.answer(
                query=arguments.query,
                knowledge_base_id=knowledge_base_id,
                top_k=arguments.top_k,
            )
            return asdict(result)

        return ToolDefinition(
            name="knowledge_rag",
            description="检索当前指定知识库中的相关资料，并生成带来源引用的回答。",
            parameters_model=BoundRAGToolArguments,
            handler=bound_handler,
        )

    async def handler(arguments: RAGToolArguments) -> dict[str, Any]:
        result = await rag_service.answer(
            query=arguments.query,
            knowledge_base_id=arguments.knowledge_base_id,
            top_k=arguments.top_k,
        )
        return asdict(result)

    return ToolDefinition(
        name="knowledge_rag",
        description="检索指定知识库中的相关资料，并生成带来源引用的回答。",
        parameters_model=RAGToolArguments,
        handler=handler,
    )
