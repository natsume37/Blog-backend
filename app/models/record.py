from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class BookRecord(Base):
    __tablename__ = "book_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    record_entry_id = Column(
        Integer,
        ForeignKey("record_entries.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    source = Column(String(30), default="weread", nullable=False, index=True)
    source_id = Column(String(80), unique=True, nullable=False, index=True)
    source_type = Column(String(30), default="book", nullable=False)

    title = Column(String(255), nullable=False)
    author = Column(String(255), default="")
    cover = Column(String(500), default="")
    category = Column(String(120), default="")
    intro = Column(Text, default="")
    publisher = Column(String(255), default="")
    publish_time = Column(String(80), default="")
    isbn = Column(String(80), default="")
    word_count = Column(Integer, default=0, nullable=False)
    weread_rating = Column(Integer, default=0, nullable=False)
    weread_rating_count = Column(Integer, default=0, nullable=False)
    chapter_count = Column(Integer, default=0, nullable=False)
    detail_synced_at = Column(DateTime, nullable=True)
    format = Column(String(50), default="微信读书")
    status = Column(String(30), default="待读", nullable=False, index=True)

    progress = Column(Integer, default=0, nullable=False)
    rating = Column(Integer, default=0, nullable=False)
    read_seconds = Column(Integer, default=0, nullable=False)
    note_count = Column(Integer, default=0, nullable=False)
    highlight_count = Column(Integer, default=0, nullable=False)
    review_count = Column(Integer, default=0, nullable=False)
    bookmark_count = Column(Integer, default=0, nullable=False)

    tags_json = Column(Text, default="[]")
    note_summary = Column(Text, default="")
    color = Column(String(20), default="#2f6c8f")
    accent = Column(String(20), default="#224c4a")

    visibility = Column(String(20), default="private", nullable=False, index=True)
    is_private = Column(Boolean, default=False, nullable=False)
    is_top = Column(Boolean, default=False, nullable=False)
    is_in_shelf = Column(Boolean, default=True, nullable=False, index=True)

    last_read_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    notes = relationship("BookNoteSummary", back_populates="book", cascade="all, delete-orphan")
    full_notes = relationship("BookNoteCache", back_populates="book", cascade="all, delete-orphan")
    record_entry = relationship("RecordEntry", back_populates="book")


class BookSearchCache(Base):
    __tablename__ = "book_search_caches"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source = Column(String(30), default="weread", nullable=False, index=True)
    source_id = Column(String(80), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False)
    author = Column(String(255), default="")
    translator = Column(String(255), default="")
    cover = Column(String(500), default="")
    intro = Column(Text, default="")
    category = Column(String(120), default="")
    publisher = Column(String(255), default="")
    publish_time = Column(String(80), default="")
    isbn = Column(String(80), default="")
    word_count = Column(Integer, default=0, nullable=False)
    rating = Column(Integer, default=0, nullable=False)
    rating_count = Column(Integer, default=0, nullable=False)
    reading_count = Column(Integer, default=0, nullable=False)
    price = Column(Integer, default=0, nullable=False)
    pay_type = Column(Integer, default=0, nullable=False)
    soldout = Column(Boolean, default=False, nullable=False)
    search_keyword = Column(String(255), default="", index=True)
    raw_json = Column(Text, default="{}")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class BookNoteCache(Base):
    __tablename__ = "book_note_caches"
    __table_args__ = (
        UniqueConstraint("source_book_id", "source_id", "note_type", name="uq_book_note_cache_source"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    book_record_id = Column(Integer, ForeignKey("book_records.id", ondelete="CASCADE"), nullable=True, index=True)
    source = Column(String(30), default="weread", nullable=False, index=True)
    source_book_id = Column(String(80), nullable=False, index=True)
    source_id = Column(String(120), nullable=False, index=True)
    note_type = Column(String(30), nullable=False, index=True)
    chapter_uid = Column(String(80), default="", index=True)
    chapter_title = Column(String(255), default="")
    content = Column(Text, default="")
    abstract = Column(Text, default="")
    location_range = Column(String(80), default="")
    color_style = Column(String(30), default="")
    deep_link = Column(String(500), default="")
    source_created_at = Column(DateTime, nullable=True)
    synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    book = relationship("BookRecord", back_populates="full_notes")


class MovieRecord(Base):
    __tablename__ = "movie_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    record_entry_id = Column(
        Integer,
        ForeignKey("record_entries.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    source = Column(String(30), default="manual", nullable=False, index=True)
    source_id = Column(String(80), unique=True, nullable=False, index=True)

    title = Column(String(255), nullable=False)
    director = Column(String(255), default="")
    cover = Column(String(500), default="")
    format = Column(String(50), default="")
    status = Column(String(30), default="想看", nullable=False, index=True)
    progress = Column(Integer, default=0, nullable=False)
    rating = Column(Integer, default=0, nullable=False)
    duration_minutes = Column(Integer, default=0, nullable=False)
    note = Column(Text, default="")
    tags_json = Column(Text, default="[]")
    color = Column(String(20), default="#2f5d7c")
    accent = Column(String(20), default="#d6a35d")
    visibility = Column(String(20), default="private", nullable=False, index=True)
    is_top = Column(Boolean, default=False, nullable=False)
    watched_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    record_entry = relationship("RecordEntry", back_populates="movie")


class BookNoteSummary(Base):
    __tablename__ = "book_note_summaries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    book_record_id = Column(Integer, ForeignKey("book_records.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id = Column(String(100), nullable=False, index=True)
    note_type = Column(String(30), nullable=False)
    chapter_title = Column(String(255), default="")
    content_summary = Column(Text, default="")
    deep_link = Column(String(500), default="")
    source_created_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    book = relationship("BookRecord", back_populates="notes")


class WeReadSyncState(Base):
    __tablename__ = "weread_sync_state"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(50), unique=True, nullable=False, default="weread")
    status = Column(String(30), default="not_configured", nullable=False)
    message = Column(String(255), default="")
    last_error = Column(Text, default="")
    last_started_at = Column(DateTime, nullable=True)
    last_finished_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    books_synced = Column(Integer, default=0, nullable=False)
    notes_synced = Column(Integer, default=0, nullable=False)
    stats_json = Column(Text, default="{}")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
