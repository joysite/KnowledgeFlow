"""KnowledgeFlow 文档文本分块模块。"""

import re
from dataclasses import dataclass, field

from app.ingestion.token_counter import OffsetTokenCounter


@dataclass(frozen=True, slots=True)
class TextChunk:
    """文档分块结果，不依赖数据库模型。"""

    chunk_index: int
    content: str
    start_index: int
    end_index: int
    token_count: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验分块数据。"""
        if self.chunk_index < 0:
            raise ValueError("chunk_index 不能小于 0")

        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("content 不能为空")

        if self.start_index < 0 or self.end_index <= self.start_index:
            raise ValueError("分块字符索引范围无效")

        if self.end_index - self.start_index != len(self.content):
            raise ValueError("分块长度与字符索引范围不一致")

        if self.token_count is not None and self.token_count < 0:
            raise ValueError("token_count 不能小于 0")

        if not isinstance(self.metadata, dict):
            raise TypeError("metadata 必须是字典")


class TextChunker:
    """按照段落、句子和字符边界切分文本。"""

    _PARAGRAPH_PATTERN = re.compile(r"\n[ \t]*\n+")
    _SENTENCE_PATTERN = re.compile(r"""[。！？!?；;.!][”’"'）】」』]*""")
    _LINE_PATTERN = re.compile(r"\n")
    _WHITESPACE_PATTERN = re.compile(r"\s+")

    def __init__(
        self,
        max_chunk_size: int = 1000,
        chunk_overlap: int = 150,
        max_tokens: int | None = None,
        token_overlap: int = 0,
        token_counter: OffsetTokenCounter | None = None,
    ) -> None:
        """初始化字符分块或 Token 分块参数。"""
        if (
            isinstance(max_chunk_size, bool)
            or not isinstance(max_chunk_size, int)
            or max_chunk_size <= 0
        ):
            raise ValueError("max_chunk_size 必须是大于 0 的整数")

        if (
            isinstance(chunk_overlap, bool)
            or not isinstance(chunk_overlap, int)
            or chunk_overlap < 0
        ):
            raise ValueError("chunk_overlap 必须是非负整数")

        if chunk_overlap >= max_chunk_size:
            raise ValueError("chunk_overlap 必须小于 max_chunk_size")

        if max_tokens is not None:
            if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 3:
                raise ValueError("max_tokens 必须是大于等于 3 的整数")

            if (
                isinstance(token_overlap, bool)
                or not isinstance(token_overlap, int)
                or token_overlap < 0
            ):
                raise ValueError("token_overlap 必须是非负整数")

            if token_overlap >= max_tokens - 2:
                raise ValueError("token_overlap 必须小于正文 Token 预算")

            if token_counter is None:
                raise ValueError("Token 模式必须提供 token_counter")

            if not callable(getattr(token_counter, "count", None)):
                raise TypeError("token_counter 必须实现 count(text) 方法")

            if not callable(getattr(token_counter, "tokenize_with_offsets", None)):
                raise TypeError("token_counter 必须实现 tokenize_with_offsets(text) 方法")
        elif token_counter is not None:
            raise ValueError("提供 token_counter 时必须同时设置 max_tokens")
        elif token_overlap != 0:
            raise ValueError("字符模式不能设置 token_overlap")

        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_tokens = max_tokens
        self.token_overlap = token_overlap
        self.token_counter = token_counter

    def split(self, content: str) -> list[TextChunk]:
        """
        将清洗后的文档文本切分为多个分块。

        偏移量基于输入文本的 Python 字符索引，采用左闭右开区间。
        空文本或纯空白文本返回空列表。

        Args:
            content: Cleaner 输出的文本。

        Returns:
            按原文顺序排列的分块列表。

        Raises:
            TypeError: 输入内容不是字符串。
        """
        if not isinstance(content, str):
            raise TypeError("待分块内容必须是字符串")

        if not content.strip():
            return []

        if self.max_tokens is not None:
            return self._split_by_tokens(content)

        chunks: list[TextChunk] = []
        start = 0
        text_length = len(content)

        while start < text_length:
            limit = min(start + self.max_chunk_size, text_length)

            if limit == text_length:
                end = text_length
            else:
                end = self._find_split_position(content, start, limit)

            chunk_content = content[start:end]

            # 防止边界选择产生纯空白分块。
            if chunk_content.strip():
                chunks.append(
                    TextChunk(
                        chunk_index=len(chunks),
                        content=chunk_content,
                        start_index=start,
                        end_index=end,
                    )
                )

            if end >= text_length:
                break

            # 下一块优先从句子或段落边界开始，形成自然的文本重叠。
            next_start = self._find_overlap_start(content, start, end)

            if next_start <= start:
                raise RuntimeError("分块位置未能向前推进")

            start = next_start

        return chunks

    def _split_by_tokens(self, content: str) -> list[TextChunk]:
        """按照正文 Token 预算切分，并保留原文字符偏移。"""
        if self.token_counter is None or self.max_tokens is None:
            raise RuntimeError("Token 分块器未正确初始化")

        token_spans = self.token_counter.tokenize_with_offsets(content)
        if not token_spans:
            token_count = self.token_counter.count(content)
            if token_count > self.max_tokens:
                raise ValueError("文本无法在 Token 预算内切分")
            return [
                TextChunk(
                    chunk_index=0,
                    content=content,
                    start_index=0,
                    end_index=len(content),
                    token_count=token_count,
                )
            ]

        body_budget = self.max_tokens - 2
        chunks: list[TextChunk] = []
        token_start = 0
        char_start = 0
        token_total = len(token_spans)

        while token_start < token_total:
            token_end = min(token_start + body_budget, token_total)
            is_last = token_end == token_total

            char_end = len(content) if is_last else token_spans[token_end - 1].end_index

            if not is_last:
                natural_end = self._find_token_boundary(
                    content,
                    char_start,
                    char_end,
                )
                if natural_end is not None:
                    char_end = natural_end

            # 以实际分块重新计数，避免整段分词结果与分块结果不一致。
            while char_end > char_start:
                chunk_content = content[char_start:char_end]
                token_count = self.token_counter.count(chunk_content)

                if token_count <= self.max_tokens:
                    break

                token_end -= 1
                if token_end <= token_start:
                    raise ValueError("单个 Token 已超过分块预算")

                char_end = token_spans[token_end - 1].end_index

            if char_end <= char_start:
                raise RuntimeError("Token 分块位置未能向前推进")

            # 找出本块实际覆盖的最后一个正文 Token。
            next_token_start = token_start
            while (
                next_token_start < token_total
                and token_spans[next_token_start].end_index <= char_end
            ):
                next_token_start += 1

            if next_token_start <= token_start:
                raise RuntimeError("Token 分块未能消耗任何 Token")

            chunk_content = content[char_start:char_end]
            token_count = self.token_counter.count(chunk_content)

            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    content=chunk_content,
                    start_index=char_start,
                    end_index=char_end,
                    token_count=token_count,
                )
            )

            if self.token_overlap > 0 and next_token_start < token_total:
                # 回退指定数量的正文 Token，形成相邻分块的重叠区域。
                overlap_token_start = max(
                    token_start + 1,
                    next_token_start - self.token_overlap,
                )

                if overlap_token_start < next_token_start:
                    char_start = token_spans[overlap_token_start].start_index
                    token_start = overlap_token_start
                else:
                    char_start = char_end
                    token_start = next_token_start
            else:
                char_start = char_end
                token_start = next_token_start

        # 将最后一个 Token 后面的原文内容保留在最后一块中。
        if char_start < len(content):
            last_chunk = chunks[-1]
            final_content = content[last_chunk.start_index :]
            final_count = self.token_counter.count(final_content)

            if final_count > self.max_tokens:
                raise ValueError("最后一块超出 Token 预算")

            chunks[-1] = TextChunk(
                chunk_index=last_chunk.chunk_index,
                content=final_content,
                start_index=last_chunk.start_index,
                end_index=len(content),
                token_count=final_count,
            )

        return chunks

    def _find_token_boundary(
        self,
        content: str,
        start: int,
        limit: int,
    ) -> int | None:
        """按照实际 Token 数量选择自然文本边界。"""
        if self.max_tokens is None or self.token_counter is None:
            raise RuntimeError("Token 分块器未正确初始化")

        minimum_tokens = (self.max_tokens - 2) // 2
        patterns = (
            self._PARAGRAPH_PATTERN,
            self._SENTENCE_PATTERN,
            self._LINE_PATTERN,
            self._WHITESPACE_PATTERN,
        )

        candidates: set[int] = set()
        for pattern in patterns:
            candidates.update(
                match.end()
                for match in pattern.finditer(content, start, limit)
                if start < match.end() <= limit
            )

        valid_candidates = []
        for position in candidates:
            token_count = self.token_counter.count(content[start:position])
            if minimum_tokens <= token_count <= self.max_tokens:
                valid_candidates.append(position)

        return max(valid_candidates) if valid_candidates else None

    def _find_overlap_start(self, content: str, start: int, end: int) -> int:
        """寻找尽量靠近目标位置的自然重叠起点。"""
        if self.chunk_overlap == 0:
            return end

        target = max(start + 1, end - self.chunk_overlap)
        tolerance = max(5, self.chunk_overlap // 2)
        search_start = max(start + 1, target - tolerance)
        search_end = min(end - 1, target + tolerance)

        if search_start > search_end:
            return target

        # 优先对齐句子边界，其次对齐段落边界。
        for pattern in (self._SENTENCE_PATTERN, self._PARAGRAPH_PATTERN):
            candidates = [
                match.end()
                for match in pattern.finditer(content, search_start, search_end)
                if start < match.end() < end
            ]

            if candidates:
                return min(candidates, key=lambda position: abs(position - target))

        # 没有合适的自然边界时，退回固定字符偏移。
        return target

    def _find_split_position(self, content: str, start: int, limit: int) -> int:
        """
        按优先级寻找切分位置。

        优先级：段落边界、句子边界、换行边界、空白边界、硬切分。
        为避免频繁产生过短分块，优先边界至少应达到窗口长度的一半。
        """
        minimum_position = start + max(1, self.max_chunk_size // 2)

        patterns = (
            self._PARAGRAPH_PATTERN,
            self._SENTENCE_PATTERN,
            self._LINE_PATTERN,
            self._WHITESPACE_PATTERN,
        )

        for pattern in patterns:
            candidates = [
                match.end()
                for match in pattern.finditer(content, start, limit)
                if minimum_position <= match.end() <= limit
            ]

            if candidates:
                return max(candidates)

        return limit
