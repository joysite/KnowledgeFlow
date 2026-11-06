"""KnowledgeFlow SQLAlchemy ORM 声明式基类模块。"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# 统一数据库约束和索引命名规则，便于 Alembic 管理迁移。
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": ("fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"),
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """所有 ORM 模型的统一声明式基类。"""

    metadata = MetaData(
        naming_convention=NAMING_CONVENTION,
    )
