"""KnowledgeFlow 文档 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk
    from app.models.knowledge_base import KnowledgeBase


class Document(Base):
    """知识库文档数据模型。"""

    __tablename__ = "documents"

    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 255",
            name="name_length_valid",
        ),
        CheckConstraint(
            "file_size >= 0",
            name="file_size_non_negative",
        ),
        CheckConstraint(
            "length(content_hash) = 64",
            name="content_hash_length_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="status_valid",
        ),
        UniqueConstraint(
            "knowledge_base_id",
            "content_hash",
            name="knowledge_base_id_content_hash",
        ),
    )

    # 文档主键
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # 所属知识库 ID
    knowledge_base_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "knowledge_bases.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    # 原始文件名称
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # 文件格式，例如 pdf、docx、md、txt
    file_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    # 本地原始文件存储路径
    file_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    # 文件大小，单位字节
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 文件 SHA-256 哈希值
    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    # 文档处理状态
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    # 文档处理失败原因
    error_message: Mapped[str | None] = mapped_column(
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

    # 所属知识库
    knowledge_base: Mapped[KnowledgeBase] = relationship(
        "KnowledgeBase",
        back_populates="documents",
    )

    # 文档关联分块
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
