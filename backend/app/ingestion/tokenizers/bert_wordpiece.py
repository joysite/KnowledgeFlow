"""基于 BERT BasicTokenizer 和 WordPiece 的本地分词实现。"""

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TokenSpan:
    """Token 与原始文本字符区间的映射。"""

    token: str
    token_id: int
    start_index: int
    end_index: int


@dataclass(frozen=True, slots=True)
class _MappedChar:
    """规范化字符及其对应的原文位置。"""

    char: str
    start_index: int
    end_index: int


@dataclass(frozen=True, slots=True)
class _BasicTokenSpan:
    """BasicTokenizer 输出及其对应的原文位置。"""

    token: str
    start_index: int
    end_index: int
    char_spans: tuple[tuple[int, int], ...]


class BertWordPieceTokenizer:
    """使用 BERT 词表执行文本规范化和 WordPiece 分词。"""

    def __init__(
        self,
        vocab_path: Path | None = None,
        do_lower_case: bool = True,
        strip_accents: bool | None = None,
        tokenize_chinese_chars: bool = True,
        max_input_chars_per_word: int = 100,
    ) -> None:
        """加载词表并初始化分词规则。"""
        if max_input_chars_per_word <= 0:
            raise ValueError("max_input_chars_per_word 必须大于 0")

        if vocab_path is None:
            vocab_path = Path(__file__).parent / "vocab" / "nomic-embed-text-vocab.json"

        try:
            data = json.loads(Path(vocab_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("无法读取或解析 BERT 词表文件") from exc

        tokens = data.get("tokens")
        special_tokens = data.get("special_tokens")

        if not isinstance(tokens, list) or not tokens:
            raise ValueError("BERT 词表必须是非空列表")

        if not isinstance(special_tokens, dict):
            raise ValueError("BERT 特殊 Token 配置无效")

        if any(not isinstance(token, str) for token in tokens):
            raise ValueError("词表中的 Token 必须全部为字符串")

        if len(tokens) != len(set(tokens)):
            raise ValueError("BERT 词表存在重复 Token")

        for token, token_id in special_tokens.items():
            if (
                not isinstance(token_id, int)
                or isinstance(token_id, bool)
                or token_id < 0
                or token_id >= len(tokens)
                or tokens[token_id] != token
            ):
                raise ValueError(f"特殊 Token 配置不正确：{token}")

        required_tokens = ("[UNK]", "[CLS]", "[SEP]")
        for token in required_tokens:
            if token not in special_tokens:
                raise ValueError(f"缺少必要的特殊 Token：{token}")

        self.tokens = tokens
        self.vocab = {token: index for index, token in enumerate(tokens)}
        self.special_tokens = special_tokens
        self.never_split = set(special_tokens)
        self.unknown_token = "[UNK]"
        self.cls_token = "[CLS]"
        self.sep_token = "[SEP]"

        self.do_lower_case = do_lower_case
        self.strip_accents = do_lower_case if strip_accents is None else strip_accents
        self.tokenize_chinese_chars = tokenize_chinese_chars
        self.max_input_chars_per_word = max_input_chars_per_word

    @staticmethod
    def _is_whitespace(char: str) -> bool:
        """判断字符是否为空白字符。"""
        return char in (" ", "\t", "\n", "\r") or unicodedata.category(char) == "Zs"

    @staticmethod
    def _is_control(char: str) -> bool:
        """判断字符是否为控制字符。"""
        if char in ("\t", "\n", "\r"):
            return False
        return unicodedata.category(char) in ("Cc", "Cf")

    @staticmethod
    def _is_chinese_char(code: int) -> bool:
        """判断字符是否属于 BERT 中文字符范围。"""
        return (
            0x4E00 <= code <= 0x9FFF
            or 0x3400 <= code <= 0x4DBF
            or 0x20000 <= code <= 0x2A6DF
            or 0x2A700 <= code <= 0x2B73F
            or 0x2B740 <= code <= 0x2B81F
            or 0x2B820 <= code <= 0x2CEAF
            or 0xF900 <= code <= 0xFAFF
            or 0x2F800 <= code <= 0x2FA1F
        )

    @staticmethod
    def _is_punctuation(char: str) -> bool:
        """判断字符是否为标点符号。"""
        code = ord(char)
        if 33 <= code <= 47 or 58 <= code <= 64 or 91 <= code <= 96 or 123 <= code <= 126:
            return True
        return unicodedata.category(char).startswith("P")

    def _clean_text(self, text: str) -> str:
        """移除无效字符并规范化空白和中文字符边界。"""
        output: list[str] = []

        for char in text:
            code = ord(char)

            if code == 0 or code == 0xFFFD:
                continue

            if self._is_control(char):
                continue

            if self._is_whitespace(char):
                output.append(" ")
                continue

            if self.tokenize_chinese_chars and self._is_chinese_char(code):
                output.extend((" ", char, " "))
            else:
                output.append(char)

        return "".join(output)

    def _strip_accents(self, text: str) -> str:
        """使用 Unicode NFD 规范化并移除组合重音符号。"""
        normalized = unicodedata.normalize("NFD", text)
        return "".join(char for char in normalized if unicodedata.category(char) != "Mn")

    def _split_punctuation(self, text: str) -> list[str]:
        """将标点字符从普通文本中独立拆分。"""
        output: list[str] = []
        current: list[str] = []

        for char in text:
            if self._is_punctuation(char):
                if current:
                    output.append("".join(current))
                    current = []
                output.append(char)
            else:
                current.append(char)

        if current:
            output.append("".join(current))

        return output

    def _basic_tokenize_with_offsets(
        self,
        text: str,
    ) -> list[_BasicTokenSpan]:
        """执行 BasicTokenizer 预处理并保留原文字符位置。"""
        cleaned: list[_MappedChar] = []

        for index, char in enumerate(text):
            code = ord(char)

            if code == 0 or code == 0xFFFD or self._is_control(char):
                continue

            mapped = _MappedChar(char, index, index + 1)

            if self._is_whitespace(char):
                cleaned.append(_MappedChar(" ", index, index + 1))
                continue

            if self.tokenize_chinese_chars and self._is_chinese_char(code):
                cleaned.append(_MappedChar(" ", index, index))
                cleaned.append(mapped)
                cleaned.append(_MappedChar(" ", index, index))
            else:
                cleaned.append(mapped)

        # 按照 BasicTokenizer 原有规则切分空白。
        basic_words: list[list[_MappedChar]] = []
        current: list[_MappedChar] = []

        for item in cleaned:
            if item.char.isspace():
                if current:
                    basic_words.append(current)
                    current = []
            else:
                current.append(item)

        if current:
            basic_words.append(current)

        output: list[_BasicTokenSpan] = []

        for word in basic_words:
            original_token = "".join(item.char for item in word)
            start_index = min(item.start_index for item in word)
            end_index = max(item.end_index for item in word)

            if original_token in self.never_split:
                char_spans = tuple((item.start_index, item.end_index) for item in word)
                output.append(
                    _BasicTokenSpan(
                        original_token,
                        start_index,
                        end_index,
                        char_spans,
                    )
                )
                continue

            normalized: list[_MappedChar] = []

            for item in word:
                chars = item.char.lower() if self.do_lower_case else item.char

                for char in chars:
                    decomposed = unicodedata.normalize("NFD", char) if self.strip_accents else char

                    for normalized_char in decomposed:
                        if self.strip_accents and unicodedata.category(normalized_char) == "Mn":
                            continue

                        normalized.append(
                            _MappedChar(
                                normalized_char,
                                item.start_index,
                                item.end_index,
                            )
                        )

            # 按照原有标点拆分规则输出，同时保留字符位置。
            punctuation_parts: list[list[_MappedChar]] = []
            current_part: list[_MappedChar] = []

            for item in normalized:
                if self._is_punctuation(item.char):
                    if current_part:
                        punctuation_parts.append(current_part)
                        current_part = []
                    punctuation_parts.append([item])
                else:
                    current_part.append(item)

            if current_part:
                punctuation_parts.append(current_part)

            for part in punctuation_parts:
                if not part:
                    continue

                token = "".join(item.char for item in part)
                token_start = min(item.start_index for item in part)
                token_end = max(item.end_index for item in part)

                char_spans = tuple((item.start_index, item.end_index) for item in part)
                output.append(_BasicTokenSpan(token, token_start, token_end, char_spans))

        return output

    def _basic_tokenize(self, text: str) -> list[str]:
        """执行 BERT BasicTokenizer 预处理。"""
        return [item.token for item in self._basic_tokenize_with_offsets(text)]

    def _wordpiece_tokenize_with_offsets(
        self,
        basic_token: _BasicTokenSpan,
    ) -> list[TokenSpan]:
        """执行 WordPiece 分词并保留原文字符位置。"""
        word = basic_token.token
        chars = list(word)
        spans = basic_token.char_spans

        def unknown_span() -> list[TokenSpan]:
            return [
                TokenSpan(
                    self.unknown_token,
                    self.vocab[self.unknown_token],
                    basic_token.start_index,
                    basic_token.end_index,
                )
            ]

        if word in self.never_split:
            return [
                TokenSpan(
                    word,
                    self.vocab[word],
                    basic_token.start_index,
                    basic_token.end_index,
                )
            ]

        if len(chars) != len(spans):
            raise ValueError("BasicTokenizer 字符位置映射长度不一致")

        if len(chars) > self.max_input_chars_per_word:
            return unknown_span()

        output: list[TokenSpan] = []
        start = 0

        while start < len(chars):
            end = len(chars)
            matched = None

            while end > start:
                piece = "".join(chars[start:end])
                candidate = "▁" + piece if start == 0 else piece

                if candidate in self.vocab:
                    matched = candidate
                    break

                end -= 1

            if matched is None:
                return unknown_span()

            output.append(
                TokenSpan(
                    matched,
                    self.vocab[matched],
                    spans[start][0],
                    spans[end - 1][1],
                )
            )
            start = end

        return output

    def _wordpiece_tokenize(self, word: str) -> list[str]:
        """使用 GGUF BERT 词表执行最长匹配分词。"""
        if word in self.never_split:
            return [word]

        chars = list(word)

        if len(chars) > self.max_input_chars_per_word:
            return [self.unknown_token]

        output: list[str] = []
        start = 0

        while start < len(chars):
            end = len(chars)
            matched = None

            while end > start:
                piece = "".join(chars[start:end])
                candidate = "▁" + piece if start == 0 else piece

                if candidate in self.vocab:
                    matched = candidate
                    break

                end -= 1

            if matched is None:
                return [self.unknown_token]

            output.append(matched)
            start = end

        return output

    def tokenize_with_offsets(self, text: str) -> list[TokenSpan]:
        """将文本转换为 Token，并返回对应的原文字符区间。"""
        if not isinstance(text, str):
            raise TypeError("待分词内容必须是字符串")

        basic_tokens = self._basic_tokenize_with_offsets(text)
        output: list[TokenSpan] = []

        for basic_token in basic_tokens:
            output.extend(self._wordpiece_tokenize_with_offsets(basic_token))

        return output

    def tokenize(self, text: str) -> list[str]:
        """将文本转换为不包含 CLS 和 SEP 的 Token 列表。"""
        return [item.token for item in self.tokenize_with_offsets(text)]

    def encode(
        self,
        text: str,
        add_special_tokens: bool = True,
    ) -> list[int]:
        """将文本转换为 Token ID 列表。"""
        tokens = self.tokenize(text)

        if add_special_tokens:
            tokens = [self.cls_token, *tokens, self.sep_token]

        return [self.vocab[token] for token in tokens]
