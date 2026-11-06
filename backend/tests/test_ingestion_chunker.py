"""KnowledgeFlow 文本分块测试。"""

import pytest

from app.ingestion.chunker import TextChunk, TextChunker
from app.ingestion.token_counter import NomicTokenCounter


def test_chunker_returns_empty_list_for_empty_content() -> None:
    """空文本不产生分块。"""
    assert TextChunker().split("") == []


def test_chunker_returns_empty_list_for_whitespace_content() -> None:
    """纯空白文本不产生分块。"""
    assert TextChunker().split(" \n\t\n ") == []


def test_chunker_keeps_short_content_in_one_chunk() -> None:
    """短文本只产生一个分块。"""
    content = "KnowledgeFlow 文档知识库"

    chunks = TextChunker().split(content)

    assert len(chunks) == 1
    assert chunks[0].content == content
    assert chunks[0].start_index == 0
    assert chunks[0].end_index == len(content)


def test_chunker_assigns_sequential_indexes() -> None:
    """分块序号从 0 开始连续递增。"""
    content = "A" * 2500

    chunks = TextChunker(max_chunk_size=500, chunk_overlap=50).split(content)

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_chunker_respects_max_chunk_size() -> None:
    """所有分块均不超过最大字符数。"""
    content = "知识库内容。" * 500

    chunks = TextChunker(max_chunk_size=300, chunk_overlap=50).split(content)

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 300 for chunk in chunks)


def test_chunker_prefers_paragraph_boundaries() -> None:
    """多个段落优先在段落边界切分。"""
    paragraphs = [f"段落{i}。" + "内容" * 35 for i in range(5)]
    content = "\n\n".join(paragraphs)

    chunks = TextChunker(max_chunk_size=180, chunk_overlap=20).split(content)

    assert len(chunks) > 1
    assert all(content[chunk.start_index : chunk.end_index] == chunk.content for chunk in chunks)


def test_chunker_splits_long_paragraph_by_sentences() -> None:
    """超长段落优先按照句子边界切分。"""
    sentences = [f"这是第{i}个句子。" for i in range(30)]
    content = "".join(sentences)

    chunks = TextChunker(max_chunk_size=100, chunk_overlap=20).split(content)

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 100 for chunk in chunks)


def test_chunker_supports_english_sentence_boundaries() -> None:
    """支持英文句号、问号和感叹号边界。"""
    content = "First sentence. Second sentence! Third sentence? Fourth sentence."

    chunks = TextChunker(max_chunk_size=35, chunk_overlap=5).split(content)

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 35 for chunk in chunks)


def test_chunker_hard_splits_very_long_sentence() -> None:
    """单个超长句子最终按字符上限硬切分。"""
    content = "A" * 500

    chunks = TextChunker(max_chunk_size=100, chunk_overlap=20).split(content)

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 100 for chunk in chunks)


def test_chunker_creates_exact_overlap() -> None:
    """相邻分块按照原文字符位置产生准确重叠。"""
    content = "A" * 500

    chunks = TextChunker(max_chunk_size=100, chunk_overlap=20).split(content)

    assert len(chunks) > 1

    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert previous.end_index - current.start_index == 20
        assert previous.content[-20:] == current.content[:20]


def test_chunker_preserves_source_offsets() -> None:
    """每个分块都能通过字符偏移量还原原文切片。"""
    content = "这是知识库测试文本。" * 100

    chunks = TextChunker(max_chunk_size=100, chunk_overlap=20).split(content)

    for chunk in chunks:
        assert content[chunk.start_index : chunk.end_index] == chunk.content
        assert chunk.end_index - chunk.start_index == len(chunk.content)


def test_chunker_supports_chinese_character_offsets() -> None:
    """中文字符偏移量按照 Python 字符索引计算。"""
    content = "知识库系统。人工智能。" * 100

    chunks = TextChunker(max_chunk_size=50, chunk_overlap=10).split(content)

    assert len(chunks) > 1

    for chunk in chunks:
        assert content[chunk.start_index : chunk.end_index] == chunk.content


def test_chunker_preserves_original_order() -> None:
    """所有分块按照原文顺序排列。"""
    content = "".join(f"[{i:04d}]" for i in range(300))

    chunks = TextChunker(max_chunk_size=100, chunk_overlap=15).split(content)

    assert chunks[0].start_index == 0
    assert all(
        current.start_index > previous.start_index
        for previous, current in zip(chunks, chunks[1:], strict=False)
    )


def test_chunker_token_count_is_not_fabricated() -> None:
    """未接入 Tokenizer 时不伪造 Token 数量。"""
    chunks = TextChunker().split("KnowledgeFlow")

    assert chunks[0].token_count is None


def test_chunker_is_deterministic() -> None:
    """相同输入和参数产生完全一致的结果。"""
    content = "知识库检索测试。" * 200
    chunker = TextChunker(max_chunk_size=100, chunk_overlap=20)

    assert chunker.split(content) == chunker.split(content)


@pytest.mark.parametrize(
    ("max_chunk_size", "chunk_overlap"),
    [
        (0, 0),
        (-1, 0),
        (100, -1),
        (100, 100),
        (True, 0),
        (100, True),
    ],
)
def test_chunker_rejects_invalid_parameters(
    max_chunk_size: int,
    chunk_overlap: int,
) -> None:
    """拒绝非法分块参数。"""
    with pytest.raises(ValueError):
        TextChunker(
            max_chunk_size=max_chunk_size,
            chunk_overlap=chunk_overlap,
        )


def test_chunker_accepts_valid_token_mode_parameters() -> None:
    """接受合法的 Token 模式参数。"""
    counter = NomicTokenCounter()

    chunker = TextChunker(
        max_tokens=512,
        token_overlap=64,
        token_counter=counter,
    )

    assert chunker.max_tokens == 512
    assert chunker.token_overlap == 64
    assert chunker.token_counter is counter


@pytest.mark.parametrize("max_tokens", [None, 0, 1, 2, -1, True, 3.5])
def test_chunker_rejects_invalid_token_budget(max_tokens: object) -> None:
    """拒绝非法 Token 预算。"""
    with pytest.raises(ValueError):
        TextChunker(
            max_tokens=max_tokens,  # type: ignore[arg-type]
            token_counter=NomicTokenCounter(),
        )


@pytest.mark.parametrize("token_overlap", [-1, True, 3.5, 510])
def test_chunker_rejects_invalid_token_overlap(token_overlap: object) -> None:
    """拒绝非法 Token 重叠参数。"""
    with pytest.raises(ValueError):
        TextChunker(
            max_tokens=512,
            token_overlap=token_overlap,  # type: ignore[arg-type]
            token_counter=NomicTokenCounter(),
        )


def test_chunker_rejects_token_mode_without_counter() -> None:
    """Token 模式必须提供计数器。"""
    with pytest.raises(ValueError, match="必须提供 token_counter"):
        TextChunker(max_tokens=512)


def test_chunker_rejects_counter_without_offset_method() -> None:
    """Token 模式拒绝缺少偏移接口的计数器。"""

    class CountOnlyCounter:
        def count(self, text: str) -> int:
            return len(text)

    with pytest.raises(TypeError, match="tokenize_with_offsets"):
        TextChunker(
            max_tokens=512,
            token_counter=CountOnlyCounter(),  # type: ignore[arg-type]
        )


def test_chunker_rejects_counter_without_count_method() -> None:
    """Token 模式拒绝缺少计数接口的对象。"""

    class OffsetOnlyCounter:
        def tokenize_with_offsets(self, text: str) -> list:
            return []

    with pytest.raises(TypeError, match="count"):
        TextChunker(
            max_tokens=512,
            token_counter=OffsetOnlyCounter(),  # type: ignore[arg-type]
        )


def test_chunker_rejects_token_counter_in_character_mode() -> None:
    """字符模式不能单独传入 Token 计数器。"""
    with pytest.raises(ValueError, match="同时设置 max_tokens"):
        TextChunker(token_counter=NomicTokenCounter())


def test_chunker_rejects_token_overlap_in_character_mode() -> None:
    """字符模式不能设置 Token 重叠。"""
    with pytest.raises(ValueError, match="不能设置 token_overlap"):
        TextChunker(token_overlap=10)


@pytest.mark.parametrize("content", [None, 123, b"knowledge"])
def test_chunker_rejects_non_string_content(content: object) -> None:
    """拒绝非字符串输入。"""
    with pytest.raises(TypeError):
        TextChunker().split(content)  # type: ignore[arg-type]


def test_text_chunk_rejects_invalid_index_range() -> None:
    """分块数据的字符索引范围必须有效。"""
    with pytest.raises(ValueError):
        TextChunk(
            chunk_index=0,
            content="hello",
            start_index=0,
            end_index=4,
        )


def test_text_chunk_rejects_negative_token_count() -> None:
    """Token 数量不能为负数。"""
    with pytest.raises(ValueError):
        TextChunk(
            chunk_index=0,
            content="hello",
            start_index=0,
            end_index=5,
            token_count=-1,
        )


def test_chunker_splits_chinese_sentences_without_spaces() -> None:
    """中文句号后没有空格时，仍然优先在句子边界切分。"""
    content = "这是第一句。" * 40

    chunks = TextChunker(max_chunk_size=50, chunk_overlap=10).split(content)

    assert len(chunks) > 1
    assert chunks[0].content.endswith("。")


def test_chunker_aligns_overlap_with_chinese_sentence_boundary() -> None:
    """重叠起点优先对齐中文句子边界。"""
    content = "这是第一句话。" * 40

    chunks = TextChunker(max_chunk_size=50, chunk_overlap=15).split(content)

    assert len(chunks) > 1
    assert chunks[1].start_index == 35
    assert content[chunks[1].start_index - 1] == "。"


def test_chunker_aligns_overlap_with_paragraph_boundary() -> None:
    """找不到附近的句子边界时，重叠起点对齐段落边界。"""
    content = "A" * 18 + "\n\n" + "B" * 18 + "\n\n" + "C" * 18

    chunks = TextChunker(max_chunk_size=50, chunk_overlap=15).split(content)

    assert len(chunks) > 1
    assert chunks[1].start_index == 20
    assert content[chunks[1].start_index - 2 : chunks[1].start_index] == "\n\n"


def test_chunker_preserves_source_slices_after_overlap_alignment() -> None:
    """自然边界对齐后仍然保持原文偏移量准确。"""
    content = "这是第一句话。" * 40

    chunks = TextChunker(max_chunk_size=50, chunk_overlap=15).split(content)

    assert chunks[0].start_index == 0
    assert chunks[-1].end_index == len(content)

    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.start_index < previous.end_index
        assert current.start_index > previous.start_index
        assert current.content == content[current.start_index : current.end_index]


def test_chunker_keeps_zero_overlap_behavior() -> None:
    """重叠长度为 0 时，相邻分块不产生重叠。"""
    content = "A" * 250

    chunks = TextChunker(max_chunk_size=100, chunk_overlap=0).split(content)

    assert len(chunks) > 1

    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert previous.end_index == current.start_index


@pytest.fixture
def token_counter() -> NomicTokenCounter:
    """创建 Token 分块测试使用的计数器。"""
    return NomicTokenCounter()


def test_token_chunker_respects_token_budget(
    token_counter: NomicTokenCounter,
) -> None:
    """Token 模式下每个分块均不得超过 Token 预算。"""
    content = "KnowledgeFlow is a local-first knowledge management system. " * 12
    chunker = TextChunker(
        max_tokens=16,
        token_overlap=0,
        token_counter=token_counter,
    )

    chunks = chunker.split(content)

    assert len(chunks) > 1
    assert all(chunk.token_count is not None for chunk in chunks)
    assert all(chunk.token_count <= 16 for chunk in chunks)


def test_token_chunker_preserves_source_offsets(
    token_counter: NomicTokenCounter,
) -> None:
    """Token 分块必须保留原文连续切片和准确偏移。"""
    content = "KnowledgeFlow 是本地优先的知识库系统。 " * 12
    chunker = TextChunker(
        max_tokens=16,
        token_overlap=0,
        token_counter=token_counter,
    )

    chunks = chunker.split(content)

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.content == content[chunk.start_index : chunk.end_index]
        assert chunk.end_index - chunk.start_index == len(chunk.content)


def test_token_chunker_counts_special_tokens(
    token_counter: NomicTokenCounter,
) -> None:
    """Token 分块的 token_count 应包含 CLS 和 SEP。"""
    content = "hello world"
    chunker = TextChunker(
        max_tokens=8,
        token_overlap=0,
        token_counter=token_counter,
    )

    chunks = chunker.split(content)

    assert len(chunks) == 1
    assert chunks[0].content == content
    assert chunks[0].token_count == token_counter.count(content)
    assert chunks[0].token_count == len(token_counter.tokenize_with_offsets(content)) + 2


def test_token_chunker_keeps_short_content_in_one_chunk(
    token_counter: NomicTokenCounter,
) -> None:
    """Token 预算足够时，短文本保持为一个分块。"""
    content = "KnowledgeFlow 是本地知识库。"
    chunker = TextChunker(
        max_tokens=64,
        token_overlap=0,
        token_counter=token_counter,
    )

    chunks = chunker.split(content)

    assert len(chunks) == 1
    assert chunks[0].content == content
    assert chunks[0].start_index == 0
    assert chunks[0].end_index == len(content)
    assert chunks[0].token_count == token_counter.count(content)


def test_token_chunker_ignores_character_chunk_size(
    token_counter: NomicTokenCounter,
) -> None:
    """Token 模式不受字符模式 max_chunk_size 限制。"""
    content = "hello world. " * 20
    chunker = TextChunker(
        max_chunk_size=5,
        chunk_overlap=0,
        max_tokens=12,
        token_overlap=0,
        token_counter=token_counter,
    )

    chunks = chunker.split(content)

    assert len(chunks) > 1
    assert any(len(chunk.content) > 5 for chunk in chunks)
    assert all(chunk.token_count is not None for chunk in chunks)
    assert all(chunk.token_count <= 12 for chunk in chunks)


def test_token_chunker_avoids_undersized_natural_chunks(
    token_counter: NomicTokenCounter,
) -> None:
    """中英文混合文本应优先选择 Token 数量足够的自然边界。"""
    content = (
        "KnowledgeFlow is a local-first knowledge management system. "
        "它支持文档解析、向量检索和 Agent 工具调用。"
    ) * 20
    max_tokens = 16
    chunker = TextChunker(
        max_tokens=max_tokens,
        token_overlap=0,
        token_counter=token_counter,
    )

    chunks = chunker.split(content)

    assert len(chunks) > 1
    assert all(
        chunk.token_count is not None and chunk.token_count <= max_tokens for chunk in chunks
    )

    # 非末尾分块应尽量使用至少一半的正文 Token 预算。
    minimum_expected = (max_tokens - 2) // 2
    assert all(chunk.token_count >= minimum_expected for chunk in chunks[:-1])


def test_token_chunker_applies_token_overlap(
    token_counter: NomicTokenCounter,
) -> None:
    """Token 模式应在相邻分块之间保留指定数量的重叠 Token。"""
    content = (
        "KnowledgeFlow is a local-first knowledge management system. "
        "It supports document parsing and semantic retrieval. "
    ) * 20
    chunker = TextChunker(
        max_tokens=24,
        token_overlap=5,
        token_counter=token_counter,
    )

    chunks = chunker.split(content)

    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.start_index < previous.end_index
        overlap = content[current.start_index : previous.end_index]
        overlap_tokens = len(token_counter.tokenize_with_offsets(overlap))
        assert 4 <= overlap_tokens <= 6


def test_token_chunker_zero_overlap_preserves_contiguous_offsets(
    token_counter: NomicTokenCounter,
) -> None:
    """Token 重叠量为零时，相邻分块应保持连续且不重叠。"""
    content = "KnowledgeFlow supports local document parsing and retrieval. " * 15
    chunker = TextChunker(
        max_tokens=16,
        token_overlap=0,
        token_counter=token_counter,
    )

    chunks = chunker.split(content)

    assert len(chunks) > 1
    assert chunks[0].start_index == 0
    assert chunks[-1].end_index == len(content)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert previous.end_index == current.start_index


def test_token_chunker_overlap_respects_token_budget(
    token_counter: NomicTokenCounter,
) -> None:
    """启用 Token 重叠后，每个分块仍不得超过 Token 预算。"""
    content = (
        "KnowledgeFlow supports local document parsing, semantic retrieval, "
        "and Agent tool invocation. "
    ) * 30
    max_tokens = 24
    chunker = TextChunker(
        max_tokens=max_tokens,
        token_overlap=5,
        token_counter=token_counter,
    )

    chunks = chunker.split(content)

    assert len(chunks) > 1
    assert all(
        chunk.token_count is not None and chunk.token_count <= max_tokens for chunk in chunks
    )
    assert all(chunk.content == content[chunk.start_index : chunk.end_index] for chunk in chunks)


def test_token_chunker_overlap_with_mixed_language(
    token_counter: NomicTokenCounter,
) -> None:
    """中英文混合文本应保持合理的 Token 重叠量。"""
    content = (
        "KnowledgeFlow 支持本地文档解析、向量检索和 Agent 工具调用。"
        " It provides semantic search and document management. "
    ) * 20
    max_tokens = 24
    chunker = TextChunker(
        max_tokens=max_tokens,
        token_overlap=5,
        token_counter=token_counter,
    )

    chunks = chunker.split(content)

    assert len(chunks) > 1
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.start_index < previous.end_index
        overlap = content[current.start_index : previous.end_index]
        overlap_tokens = len(token_counter.tokenize_with_offsets(overlap))
        assert 3 <= overlap_tokens <= 7

    assert all(
        chunk.token_count is not None and chunk.token_count <= max_tokens for chunk in chunks
    )
    assert all(chunk.content == content[chunk.start_index : chunk.end_index] for chunk in chunks)
