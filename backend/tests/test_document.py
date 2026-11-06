"""KnowledgeFlow Document ORM 模型元数据测试。"""

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint

from app.models import Document, KnowledgeBase


def test_document_table_name():
    """验证文档表名称。"""
    assert Document.__tablename__ == "documents"


def test_document_required_columns():
    """验证文档模型包含必要字段。"""
    required_columns = {
        "id",
        "knowledge_base_id",
        "name",
        "file_type",
        "file_path",
        "file_size",
        "content_hash",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    }

    assert required_columns.issubset(Document.__table__.columns.keys())


def test_document_primary_key():
    """验证文档主键。"""
    primary_key = Document.__table__.primary_key

    assert len(primary_key.columns) == 1
    assert primary_key.columns.id.primary_key


def test_document_column_types_and_lengths():
    """验证文档字段类型及字符串长度。"""
    columns = Document.__table__.columns

    assert columns.name.type.length == 255
    assert columns.file_type.type.length == 20
    assert columns.file_path.type.length == 1024
    assert columns.content_hash.type.length == 64
    assert columns.status.type.length == 20


def test_document_foreign_key():
    """验证文档所属知识库外键。"""
    column = Document.__table__.columns.knowledge_base_id

    foreign_keys = list(column.foreign_keys)

    assert len(foreign_keys) == 1

    foreign_key = foreign_keys[0]

    assert isinstance(foreign_key, ForeignKey)
    assert foreign_key.target_fullname == "knowledge_bases.id"
    assert foreign_key.ondelete == "CASCADE"
    assert column.nullable is False


def test_document_unique_constraint():
    """验证知识库内文档内容哈希唯一约束。"""
    constraints = [
        constraint
        for constraint in Document.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert len(constraints) == 1

    unique_constraint = constraints[0]

    assert [column.name for column in unique_constraint.columns] == [
        "knowledge_base_id",
        "content_hash",
    ]


def test_document_check_constraints():
    """验证文档字段检查约束。"""
    constraints = [
        str(constraint.sqltext)
        for constraint in Document.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    ]

    assert any("length(trim(name)) BETWEEN 1 AND 255" in sql for sql in constraints)
    assert any("file_size >= 0" in sql for sql in constraints)
    assert any("length(content_hash) = 64" in sql for sql in constraints)
    assert any(
        "status IN ('pending', 'processing', 'completed', 'failed')" in sql for sql in constraints
    )


def test_document_status_default():
    """验证文档处理状态默认值。"""
    status_column = Document.__table__.columns.status

    assert status_column.nullable is False
    assert status_column.default is not None
    assert status_column.default.arg == "pending"
    assert status_column.server_default is not None


def test_document_nullable_columns():
    """验证允许为空的字段。"""
    columns = Document.__table__.columns

    assert columns.error_message.nullable is True
    assert columns.name.nullable is False
    assert columns.file_type.nullable is False
    assert columns.file_path.nullable is False
    assert columns.file_size.nullable is False
    assert columns.content_hash.nullable is False


def test_document_timestamp_columns():
    """验证文档创建时间和更新时间配置。"""
    columns = Document.__table__.columns

    assert columns.created_at.server_default is not None

    assert columns.updated_at.server_default is not None
    assert columns.updated_at.onupdate is not None


def test_document_knowledge_base_relationship():
    """验证 Document 与 KnowledgeBase 的双向关系。"""
    document_relationship = Document.knowledge_base.property
    knowledge_base_relationship = KnowledgeBase.documents.property

    assert document_relationship.mapper.class_ is KnowledgeBase
    assert document_relationship.back_populates == "documents"

    assert knowledge_base_relationship.mapper.class_ is Document
    assert knowledge_base_relationship.back_populates == "knowledge_base"


def test_document_relationship_cascade():
    """验证知识库文档关系的级联删除配置。"""
    relationship = KnowledgeBase.documents.property

    assert "delete" in relationship.cascade
    assert "delete-orphan" in relationship.cascade
    assert relationship.passive_deletes is True
