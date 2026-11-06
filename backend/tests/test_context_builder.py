"""KnowledgeFlow RAG 上下文构建测试。"""

from types import SimpleNamespace

import pytest

from app.services.context_builder import ContextBuilder
from app.services.hybrid_search import HybridSearchResult


class FakeTokenCounter:
    """使用字符数模拟 Token 计数。"""

    def count(self, text):
        return len(text)


def make_result(chunk_id, content="测试内容"):
    """创建混合检索结果。"""
    return HybridSearchResult(
        chunk_id=chunk_id,
        document_id=chunk_id + 100,
        document_name=f"文档{chunk_id}.txt",
        chunk_index=chunk_id,
        content=content,
        token_count=10,
        vector_distance=0.1,
        bm25_score=1.0,
        rrf_score=0.03,
    )


def test_build_preserves_ranking_and_source_metadata():
    """验证上下文顺序、引用编号和来源信息一致。"""
    builder = ContextBuilder(FakeTokenCounter())
    results = [make_result(3), make_result(1)]

    built = builder.build(results)

    assert "[1] 文档：文档3.txt" in built.context
    assert "[2] 文档：文档1.txt" in built.context
    assert built.context.index("文档3.txt") < built.context.index("文档1.txt")
    assert [source.chunk_id for source in built.sources] == [3, 1]
    assert [source.source_id for source in built.sources] == [1, 2]
    assert built.sources[0].document_id == 103
    assert built.sources[0].chunk_index == 3
    assert built.sources[0].content == "测试内容"
    assert built.sources[0].rrf_score == 0.03
    assert built.token_count == len(built.context)


def test_build_returns_empty_context_for_empty_results():
    """验证无检索结果时返回空上下文。"""
    builder = ContextBuilder(FakeTokenCounter())

    built = builder.build([])

    assert built.context == ""
    assert built.token_count == 0
    assert built.sources == []


def test_build_stops_when_next_chunk_exceeds_budget():
    """验证超出预算后停止添加，不跳过当前片段。"""
    results = [make_result(1, "短内容"), make_result(2, "很长" * 100), make_result(3)]
    builder = ContextBuilder(FakeTokenCounter(), max_context_tokens=100)

    built = builder.build(results)

    assert [source.chunk_id for source in built.sources] == [1]
    assert "[1]" in built.context
    assert "[2]" not in built.context
    assert "[3]" not in built.context
    assert built.token_count <= 100


def test_build_does_not_truncate_first_chunk():
    """验证首个片段超出预算时不截断正文或生成引用。"""
    builder = ContextBuilder(FakeTokenCounter(), max_context_tokens=10)

    built = builder.build([make_result(1, "完整原文" * 20)])

    assert built.context == ""
    assert built.sources == []
    assert built.token_count == 0


def test_build_counts_formatted_context():
    """验证 Token 预算包含引用标记和文档元信息。"""
    builder = ContextBuilder(FakeTokenCounter())
    result = make_result(1, "正文")

    built = builder.build([result])

    assert built.token_count == len(built.context)
    assert built.token_count > len(result.content)


@pytest.mark.parametrize("limit", [0, -1])
def test_init_rejects_non_positive_token_budget(limit):
    """验证 Token 预算必须大于零。"""
    with pytest.raises(ValueError, match="必须大于 0"):
        ContextBuilder(FakeTokenCounter(), max_context_tokens=limit)


@pytest.mark.parametrize("limit", [True, 1.5, "100"])
def test_init_rejects_invalid_token_budget_type(limit):
    """验证 Token 预算必须是整数。"""
    with pytest.raises(TypeError, match="必须是整数"):
        ContextBuilder(FakeTokenCounter(), max_context_tokens=limit)


def test_build_propagates_token_counter_errors():
    """验证 Token 计数失败时向调用方传播异常。"""

    class BrokenCounter:
        def count(self, text):
            raise RuntimeError("计数失败")

    builder = ContextBuilder(BrokenCounter())

    with pytest.raises(Exception, match="Token 计数执行失败"):
        builder.build([make_result(1)])


def test_source_type_is_independent_of_search_result_instance():
    """确认测试中的结果结构与服务结果字段约定一致。"""
    result = SimpleNamespace(
        chunk_id=1,
        document_id=2,
        document_name="测试文档",
        chunk_index=0,
        content="测试正文",
        rrf_score=0.5,
    )
    builder = ContextBuilder(FakeTokenCounter())

    built = builder.build([result])

    assert len(built.sources) == 1
    assert built.sources[0].document_name == "测试文档"
