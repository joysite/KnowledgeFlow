"""KnowledgeFlow 文档分块处理模块。"""

import re
from dataclasses import replace

from app.ingestion.chunker import TextChunk, TextChunker
from app.ingestion.token_counter import TokenCounter, count_tokens


class ChunkProcessor:
    """负责分块、Token 计数和 Markdown 标题上下文提取。"""

    _HEADING_PATTERN = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+|$)(.*?)\s*$")
    _FENCE_PATTERN = re.compile(r"^ {0,3}(`{3,}|~{3,})")

    def __init__(
        self,
        chunker: TextChunker,
        token_counter: TokenCounter,
    ) -> None:
        """初始化分块处理器。"""
        if not isinstance(chunker, TextChunker):
            raise TypeError("chunker 必须是 TextChunker 类型")

        if not callable(getattr(token_counter, "count", None)):
            raise TypeError("token_counter 必须实现 count(text) 方法")

        self.chunker = chunker
        self.token_counter = token_counter

    def process(self, content: str, markdown: bool = False) -> list[TextChunk]:
        """切分文本并计算 Token 数量，可选提取 Markdown 标题路径。"""
        if not isinstance(markdown, bool):
            raise TypeError("markdown 必须是布尔值")

        chunks = self.chunker.split(content)

        # 先完成全部计数，避免向调用方返回不完整的结果。
        processed_chunks: list[TextChunk] = []

        for chunk in chunks:
            token_count = (
                chunk.token_count
                if chunk.token_count is not None
                else count_tokens(self.token_counter, chunk.content)
            )

            processed_chunks.append(
                replace(
                    chunk,
                    token_count=token_count,
                )
            )

        if markdown:
            processed_chunks = self._add_heading_paths(content, processed_chunks)

        return processed_chunks

    @classmethod
    def _add_heading_paths(
        cls,
        content: str,
        chunks: list[TextChunk],
    ) -> list[TextChunk]:
        """根据每个分块的起始位置提取 Markdown 标题层级。"""
        headings: list[tuple[int, int, str]] = []
        line_start = 0
        fence_char: str | None = None
        fence_length = 0

        for line in content.splitlines(keepends=True):
            stripped_line = line.rstrip("\r\n")
            fence_match = cls._FENCE_PATTERN.match(stripped_line)

            if fence_match:
                fence = fence_match.group(1)

                if fence_char is None:
                    fence_char = fence[0]
                    fence_length = len(fence)
                elif fence[0] == fence_char and len(fence) >= fence_length:
                    fence_char = None
                    fence_length = 0

                line_start += len(line)
                continue

            if fence_char is None:
                heading_match = cls._HEADING_PATTERN.match(stripped_line)

                if heading_match:
                    title = heading_match.group(2).strip()
                    title = re.sub(r"[ \t]+#+[ \t]*$", "", title).strip()

                    if title:
                        headings.append((line_start, len(heading_match.group(1)), title))

            line_start += len(line)

        heading_stack: dict[int, str] = {}
        heading_index = 0
        result: list[TextChunk] = []

        for chunk in chunks:
            while heading_index < len(headings) and headings[heading_index][0] <= chunk.start_index:
                _, level, title = headings[heading_index]
                heading_stack = {key: value for key, value in heading_stack.items() if key < level}
                heading_stack[level] = title
                heading_index += 1

            metadata = dict(chunk.metadata)
            metadata["heading_path"] = [heading_stack[level] for level in sorted(heading_stack)]

            result.append(replace(chunk, metadata=metadata))

        return result
