"""统一检索文本构建器测试。"""

import pytest

from app.retrieval.text_builder import RetrievalTextBuilder


def test_build_adds_heading_path_before_content():
    """验证标题层级作为检索上下文前缀。"""
    result = RetrievalTextBuilder.build(
        "执行 alembic upgrade head",
        {"heading_path": ["KnowledgeFlow", "数据库", "迁移"]},
    )

    assert result == "KnowledgeFlow > 数据库 > 迁移\n执行 alembic upgrade head"


def test_build_preserves_content_without_heading_path():
    """验证没有标题路径时原样返回正文。"""
    content = "普通文本内容"

    assert RetrievalTextBuilder.build(content) == content
    assert RetrievalTextBuilder.build(content, {}) == content
    assert RetrievalTextBuilder.build(content, {"heading_path": []}) == content
    assert (
        RetrievalTextBuilder.build(
            content,
            {"heading_path": "无效标题"},
        )
        == content
    )


def test_build_ignores_invalid_heading_items():
    """验证无效标题元素不会污染检索文本。"""
    result = RetrievalTextBuilder.build(
        "正文",
        {"heading_path": ["  数据库  ", "", None, 123, "迁移"]},
    )

    assert result == "数据库 > 迁移\n正文"


@pytest.mark.parametrize(
    ("content", "metadata", "error"),
    [
        (None, None, TypeError),
        ("正文", [], TypeError),
        ("正文", "invalid", TypeError),
    ],
)
def test_build_rejects_invalid_inputs(content, metadata, error):
    """验证构建器拒绝非法输入。"""
    with pytest.raises(error):
        RetrievalTextBuilder.build(content, metadata)


def test_build_does_not_modify_metadata_or_content():
    """验证构建过程不修改原始正文和 metadata。"""
    content = "原始正文"
    metadata = {"heading_path": ["项目", "模块"]}

    result = RetrievalTextBuilder.build(content, metadata)

    assert result == "项目 > 模块\n原始正文"
    assert content == "原始正文"
    assert metadata == {"heading_path": ["项目", "模块"]}
