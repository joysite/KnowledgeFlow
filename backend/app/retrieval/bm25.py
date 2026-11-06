"""KnowledgeFlow BM25 关键词检索算法。"""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BM25Result:
    """BM25 检索结果。"""

    document_index: int
    score: float


class BM25Retriever:
    """基于 Okapi BM25 的轻量级关键词检索器。"""

    def __init__(
        self,
        corpus: Sequence[Sequence[str]],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        """初始化语料统计信息和 IDF。"""
        if isinstance(k1, bool) or not isinstance(k1, (int, float)):
            raise TypeError("k1 必须是数字")
        if not math.isfinite(k1) or k1 <= 0:
            raise ValueError("k1 必须是有限正数")

        if isinstance(b, bool) or not isinstance(b, (int, float)):
            raise TypeError("b 必须是数字")
        if not math.isfinite(b) or not 0 <= b <= 1:
            raise ValueError("b 必须在 0 到 1 之间")

        if isinstance(corpus, (str, bytes)) or not isinstance(corpus, Sequence):
            raise TypeError("corpus 必须是 Token 序列组成的语料列表")

        self.k1 = float(k1)
        self.b = float(b)
        self.document_count = len(corpus)

        self.term_frequencies: list[Counter[str]] = []
        self.document_lengths: list[int] = []
        document_frequencies: Counter[str] = Counter()

        for tokens in corpus:
            if isinstance(tokens, (str, bytes)) or not isinstance(tokens, Sequence):
                raise TypeError("语料中的每个文档必须是 Token 序列")

            if any(not isinstance(token, str) or not token for token in tokens):
                raise ValueError("Token 必须是非空字符串")

            frequencies = Counter(tokens)
            self.term_frequencies.append(frequencies)
            self.document_lengths.append(len(tokens))
            document_frequencies.update(frequencies.keys())

        total_length = sum(self.document_lengths)
        self.average_document_length = (
            total_length / self.document_count if self.document_count else 0.0
        )

        self.inverse_document_frequencies = {
            term: math.log(1 + (self.document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequencies.items()
        }

    def search(
        self,
        query_tokens: Sequence[str],
        top_k: int = 5,
    ) -> list[BM25Result]:
        """根据查询 Token 计算 BM25 分数并返回 Top-K。"""
        if isinstance(query_tokens, (str, bytes)) or not isinstance(query_tokens, Sequence):
            raise TypeError("query_tokens 必须是 Token 序列")

        if any(not isinstance(token, str) or not token for token in query_tokens):
            raise ValueError("查询 Token 必须是非空字符串")

        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k 必须是整数")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")

        if not self.document_count:
            return []

        query_terms = set(query_tokens)
        if not query_terms:
            return []

        if self.average_document_length == 0:
            return []

        results: list[BM25Result] = []

        for index, frequencies in enumerate(self.term_frequencies):
            document_length = self.document_lengths[index]
            normalization = self.k1 * (
                1 - self.b + self.b * document_length / self.average_document_length
            )

            score = 0.0

            for term in query_terms:
                term_frequency = frequencies.get(term, 0)
                if not term_frequency:
                    continue

                idf = self.inverse_document_frequencies.get(term, 0.0)
                denominator = term_frequency + normalization

                score += idf * term_frequency * (self.k1 + 1) / denominator

            if score > 0:
                results.append(BM25Result(document_index=index, score=score))

        results.sort(key=lambda result: (-result.score, result.document_index))
        return results[:top_k]
