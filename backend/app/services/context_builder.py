"""KnowledgeFlow RAG 上下文构建模块。"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.ingestion.token_counter import NomicTokenCounter, TokenCounter, count_tokens
from app.services.hybrid_search import HybridSearchResult


@dataclass(frozen=True, slots=True)
class ContextSource:
    """上下文中的原始文档来源。"""

    source_id: int
    chunk_id: int
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    rrf_score: float


@dataclass(frozen=True, slots=True)
class BuiltContext:
    """上下文构建结果。"""

    context: str
    token_count: int
    sources: list[ContextSource]


class ContextBuilder:
    """按检索排名构建具有来源引用的 RAG 上下文。"""

    DEFAULT_MAX_CONTEXT_TOKENS = 6000

    def __init__(
        self,
        token_counter: TokenCounter | None = None,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    ) -> None:
        """初始化上下文构建器。"""
        if isinstance(max_context_tokens, bool) or not isinstance(max_context_tokens, int):
            raise TypeError("max_context_tokens 必须是整数")
        if max_context_tokens <= 0:
            raise ValueError("max_context_tokens 必须大于 0")

        self.token_counter = token_counter or NomicTokenCounter()
        self.max_context_tokens = max_context_tokens

    @staticmethod
    def _format_chunk(source_id: int, result: HybridSearchResult) -> str:
        """格式化单个检索片段及其来源标记。"""
        return (
            f"[{source_id}] 文档：{result.document_name}"
            f"（分块：{result.chunk_index}）\n"
            f"{result.content}"
        )

    def build(self, results: Sequence[HybridSearchResult]) -> BuiltContext:
        """按排名顺序构建上下文，超出预算时停止添加。"""
        if not results:
            return BuiltContext(context="", token_count=0, sources=[])

        context_parts: list[str] = []
        sources: list[ContextSource] = []
        current_token_count = 0

        for result in results:
            source_id = len(sources) + 1
            formatted_chunk = self._format_chunk(source_id, result)

            candidate_parts = [*context_parts, formatted_chunk]
            candidate_context = "\n\n".join(candidate_parts)
            candidate_token_count = count_tokens(
                self.token_counter,
                candidate_context,
            )

            if candidate_token_count > self.max_context_tokens:
                break

            context_parts.append(formatted_chunk)
            sources.append(
                ContextSource(
                    source_id=source_id,
                    chunk_id=result.chunk_id,
                    document_id=result.document_id,
                    document_name=result.document_name,
                    chunk_index=result.chunk_index,
                    content=result.content,
                    rrf_score=result.rrf_score,
                )
            )
            current_token_count = candidate_token_count

        return BuiltContext(
            context="\n\n".join(context_parts),
            token_count=current_token_count,
            sources=sources,
        )
