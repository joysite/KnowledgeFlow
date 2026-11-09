"""KnowledgeFlow 知识库 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document


class KnowledgeBase(Base):
    """知识库数据模型。"""

    __tablename__ = "knowledge_bases"

    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 128",
            name="name_length_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'deleting')",
            name="status_valid",
        ),
    )

    # 知识库主键
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # 知识库名称
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    # 知识库描述
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # 知识库生命周期状态
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )

    # 最近一次删除清理失败原因
    deletion_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # 创建时间：数据库使用 UTC 时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    # 更新时间：数据库使用 UTC 时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # 知识库关联文档
    documents: Mapped[list[Document]] = relationship(
        "Document",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
