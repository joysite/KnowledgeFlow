"""KnowledgeFlow ORM 声明式基类测试。"""

from sqlalchemy.orm import DeclarativeBase

from app.db.base import NAMING_CONVENTION, Base
from app.models import KnowledgeBase


def test_base_inherits_declarative_base():
    """测试统一 ORM 基类继承 SQLAlchemy 声明式基类。"""
    assert issubclass(Base, DeclarativeBase)


def test_base_has_metadata():
    """测试 ORM 基类具有统一的 MetaData。"""
    assert Base.metadata is not None


def test_base_uses_naming_convention():
    """测试 ORM 基类使用统一的数据库命名规则。"""
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def test_base_metadata_registers_knowledge_base():
    """测试 KnowledgeBase 模型已注册到统一 MetaData。"""
    assert "knowledge_bases" in Base.metadata.tables
    assert Base.metadata.tables["knowledge_bases"] is KnowledgeBase.__table__


def test_naming_convention_contains_required_rules():
    """测试命名规则覆盖主要数据库对象。"""
    required_rules = {"ix", "uq", "ck", "fk", "pk"}

    assert required_rules.issubset(Base.metadata.naming_convention.keys())
