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
    publisher: str = ""
    publish_time: str = ""
    isbn: str = ""
    word_count: int = 0
    weread_rating: float = 0
    weread_rating_count: int = 0
    chapter_count: int = 0
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
    visibility: str = "private"
    is_private: bool = False
    last_read_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    synced_at: Optional[datetime] = None
    detail_synced_at: Optional[datetime] = None


class BookRecordDetailOut(BookRecordOut):
    intro: str = ""
    notes: list[BookNoteSummaryOut] = Field(default_factory=list)


class BookSearchResultOut(BaseModel):
    source_id: str
    title: str
    author: str = ""
    translator: str = ""
    cover: str = ""
    intro: str = ""
    category: str = ""
    publisher: str = ""
    publish_time: str = ""
    isbn: str = ""
    word_count: int = 0
    rating: float = 0
    rating_count: int = 0
    reading_count: int = 0
    price: int = 0
    pay_type: int = 0
    soldout: bool = False
    source: str = "weread"
    from_cache: bool = False


class BookChapterOut(BaseModel):
    chapter_uid: str = ""
    chapter_idx: int = 0
    title: str = ""
    level: int = 1
    word_count: int = 0
    update_time: Optional[datetime] = None
    price: int = 0
    paid: bool = False
    deep_link: str = ""


class BookSourceDetailOut(BookSearchResultOut):
    progress: int = 0
    read_seconds: int = 0
    read_duration: str = "0分钟"
    status: str = "待读"
    local_record_id: Optional[int] = None
    visibility: str = "private"
    note_count: int = 0
    highlight_count: int = 0
    review_count: int = 0
    bookmark_count: int = 0
    tags: list[str] = Field(default_factory=list)
    last_read_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    detail_synced_at: Optional[datetime] = None
    chapters: list[BookChapterOut] = Field(default_factory=list)


class BookNoteItemOut(BaseModel):
    source_id: str
    note_type: str
    chapter_uid: str = ""
    chapter_title: str = ""
    content: str = ""
    abstract: str = ""
    location_range: str = ""
    color_style: str = ""
    deep_link: str = ""
    source_created_at: Optional[datetime] = None


class BookNoteChapterOut(BaseModel):
    chapter_uid: str = ""
    chapter_title: str = ""
    items: list[BookNoteItemOut] = Field(default_factory=list)


class BookNotesOut(BaseModel):
    source_id: str
    title: str = ""
    total: int = 0
    highlight_count: int = 0
    review_count: int = 0
    from_cache: bool = False
    chapters: list[BookNoteChapterOut] = Field(default_factory=list)


class BookRecommendationOut(BaseModel):
    source_id: str
    title: str
    author: str = ""
    cover: str = ""
    category: str = ""
    rating: float = 0
    rating_count: int = 0
    progress: int = 0
    read_seconds: int = 0
    read_duration: str = "0分钟"
    reason: str
    tags: list[str] = Field(default_factory=list)
    local_record_id: Optional[int] = None


class BookRecordStatsOut(BaseModel):
    total: int
    monthly_count: int
    completion_rate: int
    note_count: int
    average_rating: float
    read_seconds: int
    read_duration: str
    last_sync_at: Optional[datetime] = None


class MovieRecordOut(BaseModel):
    id: int
    source_id: str
    title: str
    director: str = ""
    cover: str = ""
    format: str = ""
    status: str
    progress: int
    rating: float
    duration_minutes: int
    duration: str
    note: str = ""
    tags: list[str]
    color: str
    accent: str
    visibility: str = "private"
    is_top: bool = False
    watched_at: Optional[datetime] = None


class MovieRecordStatsOut(BaseModel):
    total: int
    monthly_count: int
    finished_count: int
    average_rating: float
    total_duration_minutes: int
    total_duration: str


class RecordVisibilityUpdateIn(BaseModel):
    visibility: str


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
