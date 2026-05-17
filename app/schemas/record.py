from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class BookNoteSummaryOut(BaseModel):
    note_type: str
    chapter_title: str = ""
    content_summary: str = ""
    source_created_at: Optional[datetime] = None


class BookRecordOut(BaseModel):
    id: int
    source_id: str
    title: str
    author: str = ""
    cover: str = ""
    category: str = ""
    format: str = ""
    status: str
    progress: int
    rating: float
    read_seconds: int
    read_duration: str
    note_count: int
    highlight_count: int
    review_count: int
    bookmark_count: int
    tags: list[str]
    note_summary: str = ""
    color: str
    accent: str
    last_read_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    synced_at: Optional[datetime] = None


class BookRecordDetailOut(BookRecordOut):
    intro: str = ""
    notes: list[BookNoteSummaryOut] = Field(default_factory=list)


class BookRecordStatsOut(BaseModel):
    total: int
    monthly_count: int
    completion_rate: int
    note_count: int
    average_rating: float
    read_seconds: int
    read_duration: str
    last_sync_at: Optional[datetime] = None


class BookTimeSeriesPointOut(BaseModel):
    timestamp: int
    date: str
    label: str
    read_seconds: int
    read_duration: str


class BookTimeCategoryOut(BaseModel):
    name: str
    parent_name: str = ""
    reading_count: int = 0
    read_seconds: int
    read_duration: str
    percent: int


class BookTimeBookOut(BaseModel):
    source_id: str = ""
    title: str
    author: str = ""
    cover: str = ""
    read_seconds: int
    read_duration: str
    tags: list[str] = Field(default_factory=list)


class BookTimeStatsOut(BaseModel):
    total_read_seconds: int
    total_read_duration: str
    day_average_seconds: int
    day_average_duration: str
    read_days: int
    active_days: int
    compare: float = 0
    book_count: int
    note_count: int
    read_distribution_word: str = ""
    last_sync_at: Optional[datetime] = None
    daily: list[BookTimeSeriesPointOut] = Field(default_factory=list)
    categories: list[BookTimeCategoryOut] = Field(default_factory=list)
    longest_books: list[BookTimeBookOut] = Field(default_factory=list)


class WeReadSyncStatusOut(BaseModel):
    configured: bool
    enabled: bool
    status: str
    message: str = ""
    last_error: str = ""
    last_started_at: Optional[datetime] = None
    last_finished_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    books_synced: int = 0
    notes_synced: int = 0


class WeReadSyncResult(BaseModel):
    status: str
    message: str
    books_synced: int = 0
    notes_synced: int = 0
    skipped: bool = False
