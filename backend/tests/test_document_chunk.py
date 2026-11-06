"""KnowledgeFlow DocumentChunk ORM 模型元数据测试。"""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)

from app.models import Document, DocumentChunk


def test_document_chunk_table_name():
    """验证文档分块表名称。"""
    assert DocumentChunk.__tablename__ == "document_chunks"


def test_document_chunk_required_columns():
    """验证文档分块模型包含必要字段。"""
    required_columns = {
        "id",
        "document_id",
        "chunk_index",
        "content",
        "token_count",
        "start_index",
        "end_index",
        "metadata",
        "created_at",
    }

    assert required_columns.issubset(DocumentChunk.__table__.columns.keys())


def test_document_chunk_primary_key():
    """验证文档分块主键。"""
    primary_key = DocumentChunk.__table__.primary_key

    assert len(primary_key.columns) == 1
    assert primary_key.columns.id.primary_key


def test_document_chunk_column_types():
    """验证文档分块字段类型。"""
    columns = DocumentChunk.__table__.columns

    assert isinstance(columns.id.type, Integer)
    assert isinstance(columns.document_id.type, Integer)
    assert isinstance(columns.chunk_index.type, Integer)
    assert isinstance(columns.content.type, Text)
    assert isinstance(columns.token_count.type, Integer)
    assert isinstance(columns.start_index.type, Integer)
    assert isinstance(columns.end_index.type, Integer)
    assert isinstance(columns.metadata.type, JSON)
    assert isinstance(columns.created_at.type, DateTime)


def test_document_chunk_foreign_key():
    """验证文档分块所属文档外键。"""
    column = DocumentChunk.__table__.columns.document_id

    foreign_keys = list(column.foreign_keys)

    assert len(foreign_keys) == 1

    foreign_key = foreign_keys[0]

    assert isinstance(foreign_key, ForeignKey)
    assert foreign_key.target_fullname == "documents.id"
    assert foreign_key.ondelete == "CASCADE"
    assert column.nullable is False


def test_document_chunk_unique_constraint():
    """验证同一文档内分块序号唯一。"""
    constraints = [
        constraint
        for constraint in DocumentChunk.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert len(constraints) == 1

    unique_constraint = constraints[0]

    assert [column.name for column in unique_constraint.columns] == [
        "document_id",
        "chunk_index",
    ]


def test_document_chunk_check_constraints():
    """验证文档分块字段检查约束。"""
    constraints = [
        str(constraint.sqltext)
        for constraint in DocumentChunk.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    ]

    assert any("chunk_index >= 0" in sql for sql in constraints)
    assert any("length(trim(content)) > 0" in sql for sql in constraints)
    assert any("token_count >= 0" in sql for sql in constraints)
    assert any("start_index >= 0" in sql for sql in constraints)
    assert any("end_index > start_index" in sql for sql in constraints)


def test_document_chunk_metadata_configuration():
    """验证分块元数据字段映射和默认值。"""
    column = DocumentChunk.__table__.columns.metadata

    assert DocumentChunk.chunk_metadata.property.columns[0].name == "metadata"
    assert isinstance(column.type, JSON)
    assert column.nullable is False
    assert column.default is not None
    assert callable(column.default.arg)
    assert column.server_default is not None


def test_document_chunk_timestamp_configuration():
    """验证分块创建时间字段配置。"""
    column = DocumentChunk.__table__.columns.created_at

    assert column.nullable is False
    assert column.server_default is not None


def test_document_chunk_document_relationship():
    """验证 DocumentChunk 与 Document 的双向关系。"""
    chunk_relationship = DocumentChunk.document.property
    document_relationship = Document.chunks.property

    assert chunk_relationship.mapper.class_ is Document
    assert chunk_relationship.back_populates == "chunks"

    assert document_relationship.mapper.class_ is DocumentChunk
    assert document_relationship.back_populates == "document"


def test_document_chunk_relationship_cascade():
    """验证删除文档时分块关系的级联配置。"""
    relationship = Document.chunks.property

    assert "delete" in relationship.cascade
    assert "delete-orphan" in relationship.cascade
    assert relationship.passive_deletes is True
