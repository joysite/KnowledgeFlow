"""Nomic BERT WordPiece Tokenizer 测试。"""

import json

import pytest

from app.ingestion.tokenizers import BertWordPieceTokenizer


@pytest.fixture
def tokenizer() -> BertWordPieceTokenizer:
    """加载项目默认 Nomic 词表。"""
    return BertWordPieceTokenizer()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hello", ["▁hello"]),
        ("hello world", ["▁hello", "▁world"]),
        ("KnowledgeFlow", ["▁knowledge", "flow"]),
        ("HELLO", ["▁hello"]),
        ("café", ["▁cafe"]),
        ("你好", ["[UNK]", "[UNK]"]),
        (
            "中国人工智能",
            ["▁中", "▁国", "▁人", "[UNK]", "▁智", "[UNK]"],
        ),
        (
            "Hello, 世界！",
            ["▁hello", "▁,", "▁世", "[UNK]", "▁！"],
        ),
        ("😀🌽🚀", ["[UNK]"]),
        ("abc123", ["▁abc", "12", "3"]),
        ("abc-123", ["▁abc", "▁-", "▁123"]),
    ],
)
def test_tokenize_matches_nomic_vocab(
    tokenizer: BertWordPieceTokenizer,
    text: str,
    expected: list[str],
) -> None:
    """验证词首标记、词内续接和文本预处理。"""
    assert tokenizer.tokenize(text) == expected


def test_tokenize_normalizes_whitespace(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """连续空白不应产生额外 Token。"""
    assert tokenizer.tokenize("  hello   world  ") == [
        "▁hello",
        "▁world",
    ]


def test_tokenize_splits_repeated_punctuation(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """连续标点应逐个参与分词。"""
    assert tokenizer.tokenize("hello...world!!!") == [
        "▁hello",
        "▁.",
        "▁.",
        "▁.",
        "▁world",
        "▁!",
        "▁!",
        "▁!",
    ]


def test_encode_adds_special_tokens(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """默认编码应添加 CLS 和 SEP。"""
    token_ids = tokenizer.encode("hello")

    assert token_ids == [
        tokenizer.vocab["[CLS]"],
        tokenizer.vocab["▁hello"],
        tokenizer.vocab["[SEP]"],
    ]


def test_encode_can_disable_special_tokens(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """允许调用方关闭 CLS 和 SEP。"""
    assert tokenizer.encode("hello", add_special_tokens=False) == [tokenizer.vocab["▁hello"]]


def test_encode_empty_text_contains_only_special_tokens(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """空文本编码只包含 CLS 和 SEP。"""
    assert tokenizer.encode("") == [
        tokenizer.vocab["[CLS]"],
        tokenizer.vocab["[SEP]"],
    ]


def test_tokenize_rejects_non_string(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """拒绝非字符串输入。"""
    with pytest.raises(TypeError, match="必须是字符串"):
        tokenizer.tokenize(123)


def test_wordpiece_rejects_overlong_word(
    tmp_path,
) -> None:
    """超过单词字符限制时返回 UNK。"""
    tokens = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "▁a"]
    vocab_data = {
        "tokens": tokens,
        "special_tokens": {
            "[PAD]": 0,
            "[UNK]": 1,
            "[CLS]": 2,
            "[SEP]": 3,
        },
    }
    vocab_path = tmp_path / "vocab.json"
    vocab_path.write_text(
        json.dumps(vocab_data),
        encoding="utf-8",
    )

    tokenizer = BertWordPieceTokenizer(
        vocab_path=vocab_path,
        max_input_chars_per_word=3,
    )

    assert tokenizer.tokenize("abcd") == ["[UNK]"]


def test_constructor_rejects_invalid_max_input_chars() -> None:
    """最大输入字符数必须大于零。"""
    with pytest.raises(ValueError, match="必须大于 0"):
        BertWordPieceTokenizer(max_input_chars_per_word=0)


def test_constructor_rejects_missing_special_token(tmp_path) -> None:
    """词表缺少必要特殊 Token 时应报错。"""
    vocab_data = {
        "tokens": ["[PAD]", "[UNK]", "[CLS]"],
        "special_tokens": {
            "[PAD]": 0,
            "[UNK]": 1,
            "[CLS]": 2,
        },
    }
    vocab_path = tmp_path / "invalid-vocab.json"
    vocab_path.write_text(
        json.dumps(vocab_data),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="缺少必要的特殊 Token"):
        BertWordPieceTokenizer(vocab_path=vocab_path)


def test_tokenize_with_offsets_matches_wordpiece_positions(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """验证一个单词拆分成多个 WordPiece 后的位置映射。"""
    spans = tokenizer.tokenize_with_offsets("KnowledgeFlow")

    assert [(item.token, item.start_index, item.end_index) for item in spans] == [
        ("▁knowledge", 0, 9),
        ("flow", 9, 13),
    ]


def test_tokenize_with_offsets_preserves_accent_positions(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """去除重音符号后仍应映射到原始字符区间。"""
    spans = tokenizer.tokenize_with_offsets("café")

    assert len(spans) == 1
    assert spans[0].token == "▁cafe"
    assert (spans[0].start_index, spans[0].end_index) == (0, 4)


def test_tokenize_with_offsets_handles_chinese_and_punctuation(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """验证中英文、中文字符和标点的原文位置。"""
    text = "Hello, 世界！"
    spans = tokenizer.tokenize_with_offsets(text)

    assert [(item.token, text[item.start_index : item.end_index]) for item in spans] == [
        ("▁hello", "Hello"),
        ("▁,", ","),
        ("▁世", "世"),
        ("[UNK]", "界"),
        ("▁！", "！"),
    ]


def test_tokenize_with_offsets_excludes_whitespace(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """连续空白不应进入 Token 的原文区间。"""
    text = "  hello   world  "
    spans = tokenizer.tokenize_with_offsets(text)

    assert [(item.token, item.start_index, item.end_index) for item in spans] == [
        ("▁hello", 2, 7),
        ("▁world", 10, 15),
    ]


def test_tokenize_with_offsets_preserves_special_tokens(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """输入文本中的特殊 Token 应映射其完整原文区间。"""
    text = "[CLS] hello [SEP]"
    spans = tokenizer.tokenize_with_offsets(text)

    assert [(item.token, item.start_index, item.end_index) for item in spans] == [
        ("[CLS]", 0, 5),
        ("▁hello", 6, 11),
        ("[SEP]", 12, 17),
    ]


def test_tokenize_with_offsets_maps_unknown_and_overlong_words(
    tmp_path,
) -> None:
    """未知词和超长词应映射整个原始单词。"""
    tokens = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "▁a"]
    vocab_data = {
        "tokens": tokens,
        "special_tokens": {
            "[PAD]": 0,
            "[UNK]": 1,
            "[CLS]": 2,
            "[SEP]": 3,
        },
    }
    vocab_path = tmp_path / "offset-vocab.json"
    vocab_path.write_text(json.dumps(vocab_data), encoding="utf-8")

    tokenizer = BertWordPieceTokenizer(
        vocab_path=vocab_path,
        max_input_chars_per_word=3,
    )

    spans = tokenizer.tokenize_with_offsets("abcd")

    assert len(spans) == 1
    assert spans[0].token == "[UNK]"
    assert spans[0].token_id == 1
    assert (spans[0].start_index, spans[0].end_index) == (0, 4)


def test_tokenize_with_offsets_matches_existing_interfaces(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """验证偏移接口、原有分词接口和编码接口保持一致。"""
    samples = [
        "KnowledgeFlow",
        "café",
        "Hello, 世界！",
        "  hello   world  ",
        "[CLS] hello [SEP]",
        "中国人工智能",
        "",
    ]

    for text in samples:
        spans = tokenizer.tokenize_with_offsets(text)

        assert tokenizer.tokenize(text) == [item.token for item in spans]
        assert tokenizer.encode(
            text,
            add_special_tokens=False,
        ) == [item.token_id for item in spans]

        for item in spans:
            assert 0 <= item.start_index < item.end_index <= len(text)


def test_tokenize_with_offsets_handles_empty_and_invalid_input(
    tokenizer: BertWordPieceTokenizer,
) -> None:
    """空文本返回空列表，非字符串输入应报错。"""
    assert tokenizer.tokenize_with_offsets("") == []

    with pytest.raises(TypeError, match="必须是字符串"):
        tokenizer.tokenize_with_offsets(123)
