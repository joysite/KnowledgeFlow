"""文档分块处理器测试。"""

import pytest

from app.ingestion.chunk_processor import ChunkProcessor
from app.ingestion.chunker import TextChunk, TextChunker
from app.ingestion.token_counter import NomicTokenCounter, TokenCounterError


class FakeTokenCounter:
    """用于测试的模拟 Token 计数器。"""

    def __init__(
        self,
        result: int = 3,
        fail_at: int | None = None,
    ) -> None:
        self.result = result
        self.fail_at = fail_at
        self.calls: list[str] = []

    def count(self, text: str) -> int:
        self.calls.append(text)

        if self.fail_at == len(self.calls):
            raise RuntimeError("模拟 Token 计数失败")

        return self.result


def test_process_returns_chunks_with_token_counts() -> None:
    """处理结果中的所有分块都应具有 Token 数量。"""
    counter = FakeTokenCounter(result=8)
    processor = ChunkProcessor(
        chunker=TextChunker(max_chunk_size=20, chunk_overlap=0),
        token_counter=counter,
    )

    chunks = processor.process("第一段测试内容。第二段测试内容。")

    assert len(chunks) > 0
    assert all(chunk.token_count == 8 for chunk in chunks)
    assert len(counter.calls) == len(chunks)


def test_process_preserves_chunk_content_and_offsets() -> None:
    """计算 Token 数量不能改变原始文本和字符偏移量。"""
    processor = ChunkProcessor(
        chunker=TextChunker(max_chunk_size=12, chunk_overlap=0),
        token_counter=FakeTokenCounter(),
    )
    content = "KnowledgeFlow 是一个本地优先的知识库系统。"

    chunks = processor.process(content)

    for chunk in chunks:
        assert content[chunk.start_index : chunk.end_index] == chunk.content


def test_process_does_not_mutate_original_chunks() -> None:
    """处理结果应是新对象，不修改分块器生成的原始对象。"""
    chunker = TextChunker(max_chunk_size=20, chunk_overlap=0)
    original_chunks = chunker.split("这是用于测试原始分块不可变性的文本。")

    processor = ChunkProcessor(
        chunker=chunker,
        token_counter=FakeTokenCounter(result=5),
    )

    processed_chunks = processor.process("这是用于测试原始分块不可变性的文本。")

    assert all(chunk.token_count is None for chunk in original_chunks)
    assert all(chunk.token_count == 5 for chunk in processed_chunks)
    assert all(
        original is not processed
        for original, processed in zip(original_chunks, processed_chunks, strict=True)
    )


def test_process_returns_empty_list_for_empty_content() -> None:
    """空文本不应产生分块，也不应调用 Token 计数器。"""
    counter = FakeTokenCounter()
    processor = ChunkProcessor(
        chunker=TextChunker(),
        token_counter=counter,
    )

    assert processor.process("") == []
    assert processor.process("   \n  ") == []
    assert counter.calls == []


def test_process_stops_when_token_counting_fails() -> None:
    """任意分块计数失败时，整个处理过程应失败。"""
    counter = FakeTokenCounter(fail_at=2)
    processor = ChunkProcessor(
        chunker=TextChunker(max_chunk_size=10, chunk_overlap=0),
        token_counter=counter,
    )

    with pytest.raises(TokenCounterError, match="执行失败"):
        processor.process("第一段内容用于测试。第二段内容用于测试。第三段内容用于测试。")

    assert len(counter.calls) == 2


def test_process_rejects_non_string_content() -> None:
    """拒绝非字符串输入。"""
    processor = ChunkProcessor(
        chunker=TextChunker(),
        token_counter=FakeTokenCounter(),
    )

    with pytest.raises(TypeError, match="必须是字符串"):
        processor.process(None)


def test_processor_rejects_invalid_chunker() -> None:
    """初始化时拒绝无效分块器。"""
    with pytest.raises(TypeError, match="TextChunker"):
        ChunkProcessor(
            chunker=object(),
            token_counter=FakeTokenCounter(),
        )


def test_processor_rejects_invalid_token_counter() -> None:
    """初始化时拒绝未实现 count 方法的对象。"""
    with pytest.raises(TypeError, match="count"):
        ChunkProcessor(
            chunker=TextChunker(),
            token_counter=object(),
        )


def test_processor_accepts_zero_token_count() -> None:
    """允许计数器返回零。"""
    processor = ChunkProcessor(
        chunker=TextChunker(),
        token_counter=FakeTokenCounter(result=0),
    )

    chunks = processor.process("测试文本")

    assert len(chunks) == 1
    assert chunks[0].token_count == 0


def test_process_preserves_chunk_metadata() -> None:
    """处理过程应保留原始分块 metadata。"""
    chunker = TextChunker(max_chunk_size=100, chunk_overlap=0)
    processor = ChunkProcessor(
        chunker=chunker,
        token_counter=FakeTokenCounter(),
    )

    chunks = processor.process("测试 metadata 保留。")

    assert chunks[0].metadata == {}
    assert isinstance(chunks[0], TextChunk)


def test_process_with_nomic_token_counter() -> None:
    """验证 ChunkProcessor 能使用真实 Nomic Token 计数器。"""
    chunker = TextChunker(max_chunk_size=100, chunk_overlap=0)
    counter = NomicTokenCounter()
    processor = ChunkProcessor(
        chunker=chunker,
        token_counter=counter,
    )
    content = "KnowledgeFlow is a local-first knowledge management system."

    chunks = processor.process(content)

    assert len(chunks) == 1
    assert chunks[0].content == content
    assert chunks[0].token_count == counter.count(content)
    assert chunks[0].token_count == 13
    assert content[chunks[0].start_index : chunks[0].end_index] == content


def test_process_does_not_recount_existing_token_count(monkeypatch) -> None:
    """分块已有 Token 数量时，处理器不应重复计数。"""
    counter = FakeTokenCounter()
    chunker = TextChunker()

    chunks = [
        TextChunk(
            chunk_index=0,
            content="KnowledgeFlow",
            start_index=0,
            end_index=13,
            token_count=4,
        )
    ]
    monkeypatch.setattr(chunker, "split", lambda content: chunks)

    processor = ChunkProcessor(chunker, counter)
    result = processor.process("KnowledgeFlow")

    assert result[0].token_count == 4
    assert counter.calls == []


def test_process_extracts_nested_markdown_heading_paths(monkeypatch) -> None:
    """Markdown 标题应按层级形成路径，同级标题应重置下级标题。"""
    content = (
        "# 项目\n根内容\n"
        "## 安装\n安装内容\n"
        "### Linux\nLinux内容\n"
        "## 配置\n配置内容\n"
        "# 开发\n开发内容"
    )
    markers = ["根内容", "安装内容", "Linux内容", "配置内容", "开发内容"]
    chunks = [
        TextChunk(
            chunk_index=index,
            content=marker,
            start_index=content.index(marker),
            end_index=content.index(marker) + len(marker),
        )
        for index, marker in enumerate(markers)
    ]

    chunker = TextChunker()
    monkeypatch.setattr(chunker, "split", lambda _: chunks)
    processor = ChunkProcessor(chunker, FakeTokenCounter())

    result = processor.process(content, markdown=True)

    assert [chunk.metadata["heading_path"] for chunk in result] == [
        ["项目"],
        ["项目", "安装"],
        ["项目", "安装", "Linux"],
        ["项目", "配置"],
        ["开发"],
    ]


def test_process_ignores_headings_inside_markdown_fences(monkeypatch) -> None:
    """反引号和波浪号代码围栏中的标题不能进入标题路径。"""
    content = (
        "# 正文\n普通内容\n"
        "```python\n# 代码标题\n```\n"
        "~~~text\n## 代码二级标题\n~~~\n"
        "真实内容\n## 真实标题\n末尾内容"
    )
    markers = ["普通内容", "真实内容", "末尾内容"]
    chunks = [
        TextChunk(
            chunk_index=index,
            content=marker,
            start_index=content.index(marker),
            end_index=content.index(marker) + len(marker),
        )
        for index, marker in enumerate(markers)
    ]

    chunker = TextChunker()
    monkeypatch.setattr(chunker, "split", lambda _: chunks)
    processor = ChunkProcessor(chunker, FakeTokenCounter())

    result = processor.process(content, markdown=True)

    assert [chunk.metadata["heading_path"] for chunk in result] == [
        ["正文"],
        ["正文"],
        ["正文", "真实标题"],
    ]


def test_process_preserves_existing_metadata_when_adding_heading_path(
    monkeypatch,
) -> None:
    """添加标题路径不能覆盖原有分块 metadata。"""
    content = "# 项目\n测试内容"
    start = content.index("测试内容")
    original_chunk = TextChunk(
        chunk_index=0,
        content="测试内容",
        start_index=start,
        end_index=start + len("测试内容"),
        metadata={"source": "README.md"},
    )

    chunker = TextChunker()
    monkeypatch.setattr(chunker, "split", lambda _: [original_chunk])
    processor = ChunkProcessor(chunker, FakeTokenCounter())

    result = processor.process(content, markdown=True)

    assert result[0].metadata == {
        "source": "README.md",
        "heading_path": ["项目"],
    }
    assert original_chunk.metadata == {"source": "README.md"}
    assert result[0] is not original_chunk
    assert result[0].content == original_chunk.content
    assert result[0].start_index == original_chunk.start_index
    assert result[0].end_index == original_chunk.end_index
    assert result[0].token_count == 3
