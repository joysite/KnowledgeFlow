"""KnowledgeFlow RAG 服务测试。"""

import pytest

from app.services.context_builder import ContextBuilder
from app.services.hybrid_search import HybridSearchResult
from app.services.rag import RAGService


class FakeHybridSearchService:
    """模拟混合检索服务。"""

    def __init__(self, results=None, error=None):
        self.results = results if results is not None else []
        self.error = error
        self.arguments = None

    async def search(self, query, knowledge_base_id, top_k):
        self.arguments = (query, knowledge_base_id, top_k)
        if self.error is not None:
            raise self.error
        return self.results


class FakeTokenCounter:
    """使用字符数模拟 Token 计数。"""

    def count(self, text):
        return len(text)


class FakeChatService:
    """模拟 Ollama Chat 服务。"""

    def __init__(self, answer="这是基于知识库的回答 [1]。", error=None):
        self.answer_text = answer
        self.error = error
        self.messages = None
        self.called = False

    async def chat(self, messages):
        self.called = True
        self.messages = messages
        if self.error is not None:
            raise self.error
        return self.answer_text


def make_result(chunk_id=1):
    """创建混合检索结果。"""
    return HybridSearchResult(
        chunk_id=chunk_id,
        document_id=chunk_id + 100,
        document_name=f"文档{chunk_id}.txt",
        chunk_index=chunk_id - 1,
        content=f"这是第 {chunk_id} 个知识库片段。",
        token_count=20,
        vector_distance=0.1,
        bm25_score=2.5,
        rrf_score=0.03,
    )


def make_service(results=None, chat_error=None, search_error=None):
    """创建使用模拟依赖的 RAG 服务。"""
    search = FakeHybridSearchService(results, search_error)
    chat = FakeChatService(error=chat_error)
    builder = ContextBuilder(
        token_counter=FakeTokenCounter(),
        max_context_tokens=10000,
    )
    service = RAGService(search, builder, chat)
    return service, search, chat


@pytest.mark.asyncio
async def test_answer_generates_response_with_sources():
    """验证正常回答及来源信息保留。"""
    service, search, chat = make_service([make_result(1), make_result(2)])

    response = await service.answer("什么是知识库？", 3, top_k=5)

    assert response.query == "什么是知识库？"
    assert response.answer == "这是基于知识库的回答 [1]。"
    assert response.retrieved_count == 2
    assert response.context_token_count > 0
    assert [source.source_id for source in response.sources] == [1, 2]
    assert response.sources[0].chunk_id == 1
    assert response.sources[0].document_id == 101
    assert response.sources[0].document_name == "文档1.txt"
    assert search.arguments == ("什么是知识库？", 3, 5)

    assert chat.called is True
    assert len(chat.messages) == 2
    assert chat.messages[0]["role"] == "system"
    assert "[1]" in chat.messages[1]["content"]
    assert "[2]" in chat.messages[1]["content"]


@pytest.mark.asyncio
async def test_answer_returns_fallback_without_search_results():
    """验证没有检索结果时不调用 LLM。"""
    service, _, chat = make_service([])

    response = await service.answer("没有相关资料的问题", 1)

    assert response.answer == RAGService.NO_CONTEXT_ANSWER
    assert response.sources == []
    assert response.retrieved_count == 0
    assert response.context_token_count == 0
    assert chat.called is False


@pytest.mark.asyncio
async def test_answer_skips_llm_when_context_exceeds_budget():
    """验证没有片段能够放入上下文预算时不调用 LLM。"""
    search = FakeHybridSearchService([make_result()])
    chat = FakeChatService()
    builder = ContextBuilder(
        token_counter=FakeTokenCounter(),
        max_context_tokens=1,
    )
    service = RAGService(search, builder, chat)

    response = await service.answer("测试", 1)

    assert response.sources == []
    assert response.context_token_count == 0
    assert response.retrieved_count == 1
    assert chat.called is False


@pytest.mark.asyncio
async def test_answer_strips_query_before_search():
    """验证查询文本会去除首尾空白。"""
    service, search, _ = make_service([])

    response = await service.answer("  测试问题  ", 1)

    assert response.query == "测试问题"
    assert search.arguments == ("测试问题", 1, 5)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "knowledge_base_id", "top_k", "error"),
    [
        ("", 1, 5, ValueError),
        ("   ", 1, 5, ValueError),
        ("测试", 0, 5, ValueError),
        ("测试", True, 5, TypeError),
        ("测试", 1, 0, ValueError),
        ("测试", 1, True, TypeError),
    ],
)
async def test_answer_rejects_invalid_inputs(query, knowledge_base_id, top_k, error):
    """验证非法参数不会触发检索。"""
    service, search, chat = make_service([])

    with pytest.raises(error):
        await service.answer(query, knowledge_base_id, top_k)

    assert search.arguments is None
    assert chat.called is False


@pytest.mark.asyncio
async def test_answer_propagates_search_error():
    """验证检索异常向上抛出。"""
    service, _, chat = make_service(search_error=RuntimeError("检索失败"))

    with pytest.raises(RuntimeError, match="检索失败"):
        await service.answer("测试", 1)

    assert chat.called is False


@pytest.mark.asyncio
async def test_answer_propagates_chat_error():
    """验证 LLM 异常向上抛出。"""
    service, _, chat = make_service(
        [make_result()],
        chat_error=RuntimeError("模型调用失败"),
    )

    with pytest.raises(RuntimeError, match="模型调用失败"):
        await service.answer("测试", 1)

    assert chat.called is True


@pytest.mark.asyncio
async def test_answer_preserves_retrieved_count_when_context_is_limited():
    """验证检索数量与最终采用的来源数量分别统计。"""
    service, _, _ = make_service([make_result(1), make_result(2)])
    service.context_builder = ContextBuilder(
        token_counter=FakeTokenCounter(),
        max_context_tokens=75,
    )

    response = await service.answer("测试", 1)

    assert response.retrieved_count == 2
    assert len(response.sources) <= response.retrieved_count
