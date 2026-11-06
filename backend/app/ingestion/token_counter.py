"""KnowledgeFlow 文本 Token 计数接口。"""

from typing import Protocol

from app.ingestion.tokenizers import BertWordPieceTokenizer, TokenSpan


class TokenCounter(Protocol):
    """Token 计数器的结构化接口。"""

    def count(self, text: str) -> int:
        """计算文本对应的 Token 数量。"""
        ...


class OffsetTokenCounter(TokenCounter, Protocol):
    """同时支持 Token 计数和原文偏移映射的计数器。"""

    def tokenize_with_offsets(self, text: str) -> list[TokenSpan]:
        """获取正文 Token 及其在原文中的字符偏移。"""
        ...


class TokenCounterError(Exception):
    """Token 计数失败或计数结果无效。"""


class NomicTokenCounter:
    """基于 nomic-embed-text 词表的 Token 计数器。"""

    def __init__(
        self,
        tokenizer: BertWordPieceTokenizer | None = None,
    ) -> None:
        """初始化 Nomic Token 计数器。"""
        self.tokenizer = tokenizer or BertWordPieceTokenizer()

    def count(self, text: str) -> int:
        """计算文本的 Token 数量，包含 CLS 和 SEP。"""
        return len(self.tokenizer.encode(text, add_special_tokens=True))

    def tokenize_with_offsets(self, text: str) -> list[TokenSpan]:
        """获取正文 Token 及其在原文中的字符偏移，不包含 CLS 和 SEP。"""
        return self.tokenizer.tokenize_with_offsets(text)


def count_tokens(counter: TokenCounter, text: str) -> int:
    """统一执行 Token 计数并校验结果。"""
    if not isinstance(text, str):
        raise TypeError("待计算内容必须是字符串")

    count_method = getattr(counter, "count", None)
    if not callable(count_method):
        raise TokenCounterError("Token 计数器必须实现 count(text) 方法")

    try:
        token_count = count_method(text)
    except Exception as exc:
        raise TokenCounterError("Token 计数执行失败") from exc

    if isinstance(token_count, bool) or not isinstance(token_count, int):
        raise TokenCounterError("Token 计数结果必须是整数")

    if token_count < 0:
        raise TokenCounterError("Token 计数结果不能小于 0")

    return token_count
