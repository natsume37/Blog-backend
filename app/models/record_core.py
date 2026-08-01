"""跨模块记录的公共模型。

业务详情仍放在各自的扩展表中，公共表只保存权限、时间流和检索所需字段。
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


record_entry_tags = Table(
    "record_entry_tags",
    Base.metadata,
    Column(
        "record_id",
        Integer,
        ForeignKey("record_entries.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("record_tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class RecordEntry(Base):
    """时间流公共实体，模块详情通过一对一扩展表关联。"""

    __tablename__ = "record_entries"
    __table_args__ = (
        UniqueConstraint(
            "kind",
            "source",
            "source_key",
            name="uq_record_entries_kind_source_key",
        ),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    owner_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind = Column(String(30), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, default="", nullable=False)
    visibility = Column(String(20), default="private", nullable=False, index=True)
    status = Column(String(30), default="active", nullable=False)
    occurred_at = Column(DateTime, nullable=False, index=True)
    source = Column(String(30), default="manual", nullable=False)
    source_key = Column(String(120), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    owner = relationship("User")
    tags = relationship("RecordTag", secondary=record_entry_tags, back_populates="records")
    note = relationship(
        "NoteRecord",
        back_populates="record",
        uselist=False,
        cascade="all, delete-orphan",
    )
    focus = relationship(
        "FocusSession",
        back_populates="record",
        uselist=False,
        cascade="all, delete-orphan",
    )
    book = relationship("BookRecord", back_populates="record_entry", uselist=False)
    movie = relationship("MovieRecord", back_populates="record_entry", uselist=False)


class RecordTag(Base):
    """跨模块标签；同一站主下按名称唯一。"""

    __tablename__ = "record_tags"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_record_tags_owner_name"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    owner_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name = Column(String(80), nullable=False)
    slug = Column(String(100), nullable=False, index=True)
    color = Column(String(20), default="#8ca093", nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    records = relationship("RecordEntry", secondary=record_entry_tags, back_populates="tags")


class NoteRecord(Base):
    """笔记详情扩展。"""

    __tablename__ = "note_records"

    record_id = Column(
        Integer,
        ForeignKey("record_entries.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content = Column(Text, nullable=False)
    format = Column(String(20), default="markdown", nullable=False)

    record = relationship("RecordEntry", back_populates="note")


class FocusSession(Base):
    """专注详情扩展；计时事件的公共发生时间存放在 RecordEntry.occurred_at。"""

    __tablename__ = "focus_sessions"

    record_id = Column(
        Integer,
        ForeignKey("record_entries.id", ondelete="CASCADE"),
        primary_key=True,
    )
    task = Column(String(255), nullable=False)
    project = Column(String(120), nullable=True)
    started_at = Column(DateTime, nullable=False, index=True)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, default=0, nullable=False)
    target_seconds = Column(Integer, default=0, nullable=False)
    source = Column(String(30), default="manual", nullable=False)

    record = relationship("RecordEntry", back_populates="focus")
