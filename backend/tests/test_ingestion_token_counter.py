"""Token 计数接口测试。"""

import pytest

from app.ingestion.token_counter import (
    NomicTokenCounter,
    OffsetTokenCounter,
    TokenCounterError,
    count_tokens,
)


class FakeTokenCounter:
    """用于测试的模拟 Token 计数器。"""

    def __init__(self, result: int = 3) -> None:
        self.result = result
        self.received_text: str | None = None

    def count(self, text: str) -> int:
        self.received_text = text
        return self.result


def test_count_tokens_returns_counter_result() -> None:
    """正常计数时返回计数器结果。"""
    counter = FakeTokenCounter(result=12)

    result = count_tokens(counter, "KnowledgeFlow")

    assert result == 12
    assert counter.received_text == "KnowledgeFlow"


def test_count_tokens_accepts_zero() -> None:
    """允许计数结果为零。"""
    assert count_tokens(FakeTokenCounter(result=0), "") == 0


def test_count_tokens_accepts_chinese_text() -> None:
    """中文文本应原样传递给计数器。"""
    counter = FakeTokenCounter(result=5)
    text = "这是一个中文测试文档。"

    assert count_tokens(counter, text) == 5
    assert counter.received_text == text


@pytest.mark.parametrize("text", [None, 123, b"hello"])
def test_count_tokens_rejects_non_string_text(text: object) -> None:
    """拒绝非字符串输入。"""
    with pytest.raises(TypeError, match="必须是字符串"):
        count_tokens(FakeTokenCounter(), text)


@pytest.mark.parametrize("result", [None, "3", 3.5, True, False])
def test_count_tokens_rejects_non_integer_result(result: object) -> None:
    """拒绝非整数和布尔类型的计数结果。"""

    class InvalidCounter:
        def count(self, text: str) -> object:
            return result

    with pytest.raises(TokenCounterError, match="必须是整数"):
        count_tokens(InvalidCounter(), "test")


def test_count_tokens_rejects_negative_result() -> None:
    """拒绝负数计数结果。"""
    with pytest.raises(TokenCounterError, match="不能小于 0"):
        count_tokens(FakeTokenCounter(result=-1), "test")


def test_count_tokens_rejects_counter_without_count_method() -> None:
    """拒绝未实现 count 方法的对象。"""
    with pytest.raises(TokenCounterError, match="必须实现 count"):
        count_tokens(object(), "test")


def test_count_tokens_wraps_counter_exception() -> None:
    """计数器异常应转换为统一异常，并保留原始异常链。"""

    class BrokenCounter:
        def count(self, text: str) -> int:
            raise RuntimeError("tokenizer 内部错误")

    with pytest.raises(TokenCounterError, match="执行失败") as exc_info:
        count_tokens(BrokenCounter(), "test")

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "tokenizer 内部错误"


@pytest.fixture
def nomic_counter() -> NomicTokenCounter:
    """创建 Nomic Token 计数器。"""
    return NomicTokenCounter()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", 2),
        ("hello", 3),
        ("hello world", 4),
        ("KnowledgeFlow", 4),
        ("你好", 4),
        ("中国人工智能", 8),
        ("Hello, 世界！", 7),
        ("HELLO", 3),
        ("café", 3),
        ("abc123", 5),
        ("abc-123", 5),
        ("😀", 3),
    ],
)
def test_nomic_token_counter_matches_reference(
    nomic_counter: NomicTokenCounter,
    text: str,
    expected: int,
) -> None:
    """验证 Nomic Token 数量与 Ollama 参考值一致。"""
    assert nomic_counter.count(text) == expected


def test_nomic_token_counter_uses_unified_interface(
    nomic_counter: NomicTokenCounter,
) -> None:
    """验证 Nomic 计数器可以通过统一接口调用。"""
    assert count_tokens(nomic_counter, "hello") == 3


def test_offset_token_counter_declares_required_methods() -> None:
    """偏移计数接口同时要求计数和偏移映射方法。"""
    assert callable(getattr(OffsetTokenCounter, "count", None))
    assert callable(getattr(OffsetTokenCounter, "tokenize_with_offsets", None))


def test_nomic_counter_satisfies_offset_counter_interface(
    nomic_counter: NomicTokenCounter,
) -> None:
    """Nomic 计数器提供偏移接口所需的两个方法。"""
    assert callable(getattr(nomic_counter, "count", None))
    assert callable(getattr(nomic_counter, "tokenize_with_offsets", None))


def test_nomic_counter_tokenize_with_offsets(
    nomic_counter: NomicTokenCounter,
) -> None:
    """验证 Token 与原文字符区间的映射。"""
    text = "KnowledgeFlow"

    spans = nomic_counter.tokenize_with_offsets(text)

    assert [(item.token, item.start_index, item.end_index) for item in spans] == [
        ("▁knowledge", 0, 9),
        ("flow", 9, 13),
    ]
    assert all(text[item.start_index : item.end_index] for item in spans)


def test_nomic_counter_offsets_exclude_special_tokens(
    nomic_counter: NomicTokenCounter,
) -> None:
    """偏移接口不包含 CLS 和 SEP，计数接口仍包含它们。"""
    spans = nomic_counter.tokenize_with_offsets("hello")

    assert len(spans) == 1
    assert nomic_counter.count("hello") == len(spans) + 2


def test_nomic_counter_offsets_preserve_accent_positions(
    nomic_counter: NomicTokenCounter,
) -> None:
    """去除重音符号后仍然映射到原文位置。"""
    spans = nomic_counter.tokenize_with_offsets("café")

    assert len(spans) == 1
    assert spans[0].token == "▁cafe"
    assert (spans[0].start_index, spans[0].end_index) == (0, 4)


def test_nomic_counter_offsets_reject_non_string(
    nomic_counter: NomicTokenCounter,
) -> None:
    """偏移接口拒绝非字符串输入。"""
    with pytest.raises(TypeError):
        nomic_counter.tokenize_with_offsets(123)  # type: ignore[arg-type]
