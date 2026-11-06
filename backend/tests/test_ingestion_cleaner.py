"""KnowledgeFlow 文档清洗器测试。"""

import pytest

from app.ingestion.cleaner import DocumentCleaner


@pytest.fixture
def cleaner():
    """创建文档清洗器。"""
    return DocumentCleaner()


def test_cleaner_normalizes_windows_newlines(cleaner):
    """验证 Windows 换行符统一为 LF。"""
    content = "第一行\r\n第二行\r\n第三行"

    assert cleaner.clean(content) == "第一行\n第二行\n第三行"


def test_cleaner_normalizes_old_mac_newlines(cleaner):
    """验证旧式 Mac 换行符统一为 LF。"""
    content = "第一行\r第二行\r第三行"

    assert cleaner.clean(content) == "第一行\n第二行\n第三行"


def test_cleaner_removes_null_character(cleaner):
    """验证删除 NUL 字符。"""
    content = "Knowledge\x00Flow"

    assert cleaner.clean(content) == "KnowledgeFlow"


def test_cleaner_removes_other_control_characters(cleaner):
    """验证删除不适合正文的控制字符。"""
    content = "第一行\x01第二行\x7f第三行\x85第四行"

    assert cleaner.clean(content) == "第一行第二行第三行第四行"


def test_cleaner_preserves_newlines_and_tabs(cleaner):
    """验证保留换行符和行内 Tab。"""
    content = "第一列\t第二列\n第三列\t第四列"

    assert cleaner.clean(content) == content


def test_cleaner_removes_trailing_spaces_and_tabs(cleaner):
    """验证清理每行末尾的空格和 Tab。"""
    content = "第一行   \n第二行\t\t\n第三行  \t"

    assert cleaner.clean(content) == "第一行\n第二行\n第三行"


def test_cleaner_preserves_leading_indentation(cleaner):
    """验证保留行首缩进。"""
    content = "普通文本\n    缩进内容\n\tTab缩进"

    assert cleaner.clean(content) == content


def test_cleaner_collapses_multiple_blank_lines(cleaner):
    """验证连续空行最多保留一个。"""
    content = "第一段\n\n\n\n第二段"

    assert cleaner.clean(content) == "第一段\n\n第二段"


def test_cleaner_removes_leading_and_trailing_blank_lines(cleaner):
    """验证清除文档首尾多余空行。"""
    content = "\n\n第一段\n第二段\n\n"

    assert cleaner.clean(content) == "第一段\n第二段"


def test_cleaner_preserves_markdown_structure(cleaner):
    """验证保留 Markdown 标题、列表和引用结构。"""
    content = "# KnowledgeFlow\n\n## 功能\n\n- 文档解析\n- 混合检索\n\n> 知识库系统"

    assert cleaner.clean(content) == content


def test_cleaner_preserves_markdown_code_block(cleaner):
    """验证保留 Markdown 代码块及代码缩进。"""
    content = "```python\ndef hello():\n    print('hello')\n```\n"

    expected = "```python\ndef hello():\n    print('hello')\n```"

    assert cleaner.clean(content) == expected


def test_cleaner_preserves_table_tabs(cleaner):
    """验证保留 DOCX 表格的单元格分隔 Tab。"""
    content = "名称\t版本\nKnowledgeFlow\t1.0"

    assert cleaner.clean(content) == content


def test_cleaner_preserves_punctuation_and_chinese_text(cleaner):
    """验证不删除中英文标点和中文内容。"""
    content = "你好，KnowledgeFlow！Hello, World. 测试：成功。"

    assert cleaner.clean(content) == content


def test_cleaner_handles_empty_string(cleaner):
    """验证空字符串。"""
    assert cleaner.clean("") == ""


def test_cleaner_handles_only_whitespace(cleaner):
    """验证只有空白字符的内容。"""
    assert cleaner.clean(" \t\n\n \t") == ""


def test_cleaner_rejects_non_string_input(cleaner):
    """验证拒绝非字符串输入。"""
    with pytest.raises(TypeError, match="必须是字符串"):
        cleaner.clean(None)


def test_cleaner_is_idempotent(cleaner):
    """验证重复清洗不会继续改变结果。"""
    content = "\r\n\n# 标题  \r\n\r\n\r\n正文\x00  \r\n"

    once = cleaner.clean(content)
    twice = cleaner.clean(once)

    assert twice == once
