"""KnowledgeFlow 文档分块 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document


class DocumentChunk(Base):
    """文档分块数据模型。"""

    __tablename__ = "document_chunks"

    __table_args__ = (
        CheckConstraint(
            "chunk_index >= 0",
            name="chunk_index_non_negative",
        ),
        CheckConstraint(
            "length(trim(content)) > 0",
            name="content_not_empty",
        ),
        CheckConstraint(
            "token_count >= 0",
            name="token_count_non_negative",
        ),
        CheckConstraint(
            "start_index >= 0",
            name="start_index_non_negative",
        ),
        CheckConstraint(
            "end_index > start_index",
            name="index_range_valid",
        ),
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="document_id_chunk_index",
        ),
    )

    # 分块主键
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # 所属文档 ID
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # 文档内分块序号，从 0 开始
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 分块文本
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # 分块 Token 数量，由后续分块 Service 计算
    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 分块在原始文本中的起始字符位置
    start_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 分块在原始文本中的结束字符位置
    end_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 分块附加元数据，Python 属性不能直接命名为 metadata
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )

    # 创建时间：数据库使用 UTC 时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    # 所属文档
    document: Mapped[Document] = relationship(
        "Document",
        back_populates="chunks",
    )
