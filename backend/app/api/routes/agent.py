"""KnowledgeFlow Agent 智能问答 API。"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.agent import AgentExecutor
from app.api.dependencies import get_agent_executor, get_rag_service
from app.core.logging import get_logger
from app.services.knowledge_base import KnowledgeBaseService
from app.services.rag import RAGService

router = APIRouter(tags=["agent"])
logger = get_logger(__name__)


class AgentRequest(BaseModel):
    """Agent 问答请求。"""

    query: str = Field(min_length=1, max_length=10000)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("查询文本不能为空")
        return value


class AgentResponseModel(BaseModel):
    """Agent 问答响应。"""

    knowledge_base_id: int
    query: str
    answer: str
    tool_calls_count: int
    iterations: int


@router.post(
    "/knowledge-bases/{knowledge_base_id}/agent",
    response_model=AgentResponseModel,
    summary="使用 Agent 智能问答",
)
async def run_agent(
    knowledge_base_id: int,
    payload: AgentRequest,
    rag_service: RAGService = Depends(get_rag_service),
    agent_executor: AgentExecutor = Depends(get_agent_executor),
) -> AgentResponseModel:
    """执行 Agent 推理，按需调用当前知识库的 RAG 工具。"""
    knowledge_base_service = KnowledgeBaseService(rag_service.hybrid_search_service.session)
    knowledge_base = await knowledge_base_service.get_by_id(knowledge_base_id)

    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在",
        )

    try:
        result = await agent_executor.run(payload.query)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception:
        logger.exception(
            "Agent 问答失败，知识库 ID：%s",
            knowledge_base_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent 问答失败，请检查服务日志",
        ) from None

    return AgentResponseModel(
        knowledge_base_id=knowledge_base_id,
        query=payload.query,
        answer=result.answer,
        tool_calls_count=result.tool_calls_count,
        iterations=result.iterations,
    )
