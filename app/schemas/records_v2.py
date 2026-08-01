from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class RecordKind(str, Enum):
    NOTE = "note"
    FOCUS = "focus"
    READING = "reading"
    MOVIE = "movie"


class RecordVisibility(str, Enum):
    PRIVATE = "private"
    PUBLIC = "public"


class RecordModuleOut(BaseModel):
    kind: RecordKind
    label: str
    icon: str
    read_enabled: bool = True
    write_enabled: bool = False
    reason: str = ""


class TimelineRecordBase(BaseModel):
    id: str
    source_id: int
    title: str
    summary: str = ""
    visibility: RecordVisibility
    occurred_at: datetime
    created_at: datetime
    tags: list[str] = Field(default_factory=list)


class NoteTimelineDetail(BaseModel):
    content: str
    format: str = "markdown"


class FocusTimelineDetail(BaseModel):
    task: str
    project: str = ""
    duration_seconds: int = Field(ge=0)
    target_seconds: int = Field(ge=0)


class ReadingTimelineDetail(BaseModel):
    book_title: str
    author: str = ""
    progress: int = Field(ge=0, le=100)
    duration_seconds: int = Field(ge=0)
    status: str


class MovieTimelineDetail(BaseModel):
    movie_title: str
    director: str = ""
    rating: float = Field(ge=0, le=5)
    status: str
    duration_minutes: int = Field(ge=0)


class NoteTimelineRecord(TimelineRecordBase):
    kind: Literal[RecordKind.NOTE] = RecordKind.NOTE
    detail: NoteTimelineDetail


class FocusTimelineRecord(TimelineRecordBase):
    kind: Literal[RecordKind.FOCUS] = RecordKind.FOCUS
    detail: FocusTimelineDetail


class ReadingTimelineRecord(TimelineRecordBase):
    kind: Literal[RecordKind.READING] = RecordKind.READING
    detail: ReadingTimelineDetail


class MovieTimelineRecord(TimelineRecordBase):
    kind: Literal[RecordKind.MOVIE] = RecordKind.MOVIE
    detail: MovieTimelineDetail


TimelineRecordOut = Annotated[
    Union[NoteTimelineRecord, FocusTimelineRecord, ReadingTimelineRecord, MovieTimelineRecord],
    Field(discriminator="kind"),
]


class NoteRecordCreate(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    visibility: RecordVisibility = RecordVisibility.PRIVATE
    occurred_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=30)
    format: str = Field(default="markdown", min_length=1, max_length=20)
    source_key: str | None = Field(default=None, max_length=120)


class FocusRecordCreate(BaseModel):
    task: str = Field(min_length=1, max_length=255)
    project: str = Field(default="", max_length=120)
    duration_seconds: int = Field(ge=0, le=86_400)
    target_seconds: int = Field(default=0, ge=0, le=86_400)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    occurred_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=30)
    source_key: str | None = Field(default=None, max_length=120)


class ReadingRecordCreate(BaseModel):
    book_title: str = Field(min_length=1, max_length=255)
    author: str = Field(default="", max_length=255)
    progress: int = Field(default=0, ge=0, le=100)
    duration_minutes: int = Field(default=0, ge=0, le=100_000)
    status: str = Field(default="在读", min_length=1, max_length=30)
    note: str = Field(default="", max_length=100_000)
    visibility: RecordVisibility = RecordVisibility.PRIVATE
    occurred_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=30)
    source_key: str | None = Field(default=None, max_length=120)


class MovieRecordCreate(BaseModel):
    movie_title: str = Field(min_length=1, max_length=255)
    director: str = Field(default="", max_length=255)
    rating: float = Field(default=0, ge=0, le=5)
    status: str = Field(default="看过", min_length=1, max_length=30)
    duration_minutes: int = Field(default=0, ge=0, le=100_000)
    note: str = Field(default="", max_length=100_000)
    visibility: RecordVisibility = RecordVisibility.PRIVATE
    occurred_at: datetime | None = None
    tags: list[str] = Field(default_factory=list, max_length=30)
    source_key: str | None = Field(default=None, max_length=120)


class TimelinePageOut(BaseModel):
    items: list[TimelineRecordOut]
    next_cursor: str | None = None
    has_more: bool = False
