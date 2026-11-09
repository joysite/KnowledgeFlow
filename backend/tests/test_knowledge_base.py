"""KnowledgeFlow 知识库 ORM 模型测试。"""

from datetime import datetime

from sqlalchemy import CheckConstraint

from app.models import KnowledgeBase


def test_knowledge_base_table_name():
    """测试知识库数据表名称。"""
    assert KnowledgeBase.__tablename__ == "knowledge_bases"


def test_knowledge_base_primary_key():
    """测试知识库主键定义。"""
    column = KnowledgeBase.__table__.columns["id"]

    assert column.primary_key is True
    assert column.autoincrement is True


def test_knowledge_base_name_column():
    """测试知识库名称字段。"""
    column = KnowledgeBase.__table__.columns["name"]

    assert column.nullable is False
    assert column.type.length == 128


def test_knowledge_base_description_column():
    """测试知识库描述字段允许为空。"""
    column = KnowledgeBase.__table__.columns["description"]

    assert column.nullable is True


def test_knowledge_base_timestamp_columns():
    """测试知识库时间字段定义。"""
    columns = KnowledgeBase.__table__.columns

    for field_name in ("created_at", "updated_at"):
        column = columns[field_name]

        assert column.nullable is False
        assert column.type.timezone is False
        assert column.type.python_type is datetime


def test_knowledge_base_timestamp_defaults():
    """测试时间字段具有数据库默认值和更新时间机制。"""
    columns = KnowledgeBase.__table__.columns

    assert columns["created_at"].server_default is not None
    assert columns["updated_at"].server_default is not None
    assert columns["updated_at"].onupdate is not None


def test_knowledge_base_lifecycle_columns():
    """测试知识库生命周期字段定义。"""
    columns = KnowledgeBase.__table__.columns

    status = columns["status"]
    assert status.nullable is False
    assert status.type.length == 20
    assert status.default.arg == "active"
    assert status.server_default.arg == "active"

    deletion_error = columns["deletion_error"]
    assert deletion_error.nullable is True


def test_knowledge_base_check_constraints():
    """测试知识库名称和生命周期状态约束。"""
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in KnowledgeBase.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert constraints == {
        "ck_knowledge_bases_name_length_valid": ("length(trim(name)) BETWEEN 1 AND 128"),
        "ck_knowledge_bases_status_valid": "status IN ('active', 'deleting')",
    }
