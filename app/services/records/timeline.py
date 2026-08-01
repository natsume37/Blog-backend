import base64
import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.record import BookRecord, MovieRecord
from app.models.record_core import RecordEntry
from app.schemas.records_v2 import (
    FocusTimelineDetail,
    FocusTimelineRecord,
    MovieTimelineDetail,
    MovieTimelineRecord,
    NoteTimelineDetail,
    NoteTimelineRecord,
    ReadingTimelineDetail,
    ReadingTimelineRecord,
    RecordKind,
    RecordModuleOut,
    RecordVisibility,
    TimelinePageOut,
    TimelineRecordOut,
)


KIND_ORDER = {
    RecordKind.NOTE: 4,
    RecordKind.FOCUS: 3,
    RecordKind.READING: 2,
    RecordKind.MOVIE: 1,
}


class InvalidTimelineCursor(ValueError):
    pass


@dataclass(frozen=True)
class TimelineCursor:
    occurred_at: datetime
    kind: RecordKind
    source_id: int


def _encode_cursor(record: TimelineRecordOut) -> str:
    payload = {
        "occurred_at": record.occurred_at.isoformat(),
        "kind": record.kind.value,
        "source_id": record.source_id,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(value: str | None) -> TimelineCursor | None:
    if not value:
        return None

    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        occurred_at = datetime.fromisoformat(str(payload["occurred_at"]))
        kind = RecordKind(str(payload["kind"]))
        source_id = int(payload["source_id"])
        if source_id <= 0:
            raise ValueError("source_id must be positive")
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidTimelineCursor("无效或已损坏的时间流游标") from exc

    return TimelineCursor(occurred_at=occurred_at, kind=kind, source_id=source_id)


def _apply_cursor(
    statement: Select,
    occurred_expression,
    id_column,
    kind: RecordKind,
    cursor: TimelineCursor | None,
) -> Select:
    if cursor is None:
        return statement

    kind_order = KIND_ORDER[kind]
    cursor_order = KIND_ORDER[cursor.kind]
    older = occurred_expression < cursor.occurred_at

    if kind_order < cursor_order:
        return statement.where(or_(older, occurred_expression == cursor.occurred_at))
    if kind_order > cursor_order:
        return statement.where(older)
    return statement.where(
        or_(
            older,
            and_(occurred_expression == cursor.occurred_at, id_column < cursor.source_id),
        )
    )


def _load_tags(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _public_visibility(value: str | None) -> RecordVisibility:
    return RecordVisibility.PUBLIC if value == "public" else RecordVisibility.PRIVATE


def _entry_tags(record: RecordEntry) -> list[str]:
    return [tag.name for tag in record.tags if tag.name.strip()]


def _note_to_timeline(record: RecordEntry, occurred_at: datetime | None = None) -> NoteTimelineRecord:
    detail = record.note
    if detail is None:
        raise ValueError(f"笔记记录 {record.id} 缺少详情")
    actual_occurred_at = occurred_at or record.occurred_at
    return NoteTimelineRecord(
        id=f"note:{record.id}",
        source_id=record.id,
        title=record.title,
        summary=record.summary or detail.content[:120],
        visibility=_public_visibility(record.visibility),
        occurred_at=actual_occurred_at,
        created_at=record.created_at or actual_occurred_at,
        tags=_entry_tags(record),
        detail=NoteTimelineDetail(content=detail.content, format=detail.format),
    )


def _focus_to_timeline(record: RecordEntry, occurred_at: datetime | None = None) -> FocusTimelineRecord:
    detail = record.focus
    if detail is None:
        raise ValueError(f"专注记录 {record.id} 缺少详情")
    actual_occurred_at = occurred_at or record.occurred_at
    return FocusTimelineRecord(
        id=f"focus:{record.id}",
        source_id=record.id,
        title=detail.task,
        summary=record.summary or detail.project or "专注",
        visibility=_public_visibility(record.visibility),
        occurred_at=actual_occurred_at,
        created_at=record.created_at or actual_occurred_at,
        tags=_entry_tags(record),
        detail=FocusTimelineDetail(
            task=detail.task,
            project=detail.project or "",
            duration_seconds=max(0, int(detail.duration_seconds or 0)),
            target_seconds=max(0, int(detail.target_seconds or 0)),
        ),
    )


def _book_to_timeline(record: BookRecord, occurred_at: datetime) -> ReadingTimelineRecord:
    progress = max(0, min(100, int(record.progress or 0)))
    return ReadingTimelineRecord(
        id=f"reading:{record.id}",
        source_id=record.id,
        title=f"《{record.title}》读到 {progress}%",
        summary=(record.note_summary or "").strip() or (record.author or record.status or ""),
        visibility=_public_visibility(record.visibility),
        occurred_at=occurred_at,
        created_at=record.created_at or occurred_at,
        tags=_load_tags(record.tags_json),
        detail=ReadingTimelineDetail(
            book_title=record.title,
            author=record.author or "",
            progress=progress,
            duration_seconds=max(0, int(record.read_seconds or 0)),
            status=record.status or "待读",
        ),
    )


def _movie_to_timeline(record: MovieRecord, occurred_at: datetime) -> MovieTimelineRecord:
    rating = round(max(0, min(50, int(record.rating or 0))) / 10, 1)
    return MovieTimelineRecord(
        id=f"movie:{record.id}",
        source_id=record.id,
        title=f"《{record.title}》",
        summary=(record.note or "").strip() or (record.director or record.status or ""),
        visibility=_public_visibility(record.visibility),
        occurred_at=occurred_at,
        created_at=record.created_at or occurred_at,
        tags=_load_tags(record.tags_json),
        detail=MovieTimelineDetail(
            movie_title=record.title,
            director=record.director or "",
            rating=rating,
            status=record.status or "想看",
            duration_minutes=max(0, int(record.duration_minutes or 0)),
        ),
    )


def _sort_key(record: TimelineRecordOut) -> tuple[datetime, int, int]:
    return record.occurred_at, KIND_ORDER[record.kind], record.source_id


def list_timeline_records(
    db: Session,
    *,
    is_admin: bool,
    limit: int = 20,
    cursor_value: str | None = None,
) -> TimelinePageOut:
    cursor = _decode_cursor(cursor_value)
    candidate_limit = limit + 1

    # 新模块直接从公共实体表读取；旧的阅读/电影表保留在下方作为兼容读取路径。
    entry_occurred_at = RecordEntry.occurred_at
    entry_statement = (
        select(RecordEntry)
        .options(
            selectinload(RecordEntry.note),
            selectinload(RecordEntry.focus),
            selectinload(RecordEntry.tags),
        )
        .where(
            RecordEntry.kind.in_([RecordKind.NOTE.value, RecordKind.FOCUS.value]),
        )
    )
    if not is_admin:
        entry_statement = entry_statement.where(RecordEntry.visibility == "public")
    if cursor is not None:
        # 公共表中不同模块共享同一个自增主键，沿用统一时间流排序规则。
        entry_statement = entry_statement.where(
            or_(
                entry_occurred_at < cursor.occurred_at,
                and_(
                    entry_occurred_at == cursor.occurred_at,
                    or_(
                        KIND_ORDER[RecordKind.NOTE] < KIND_ORDER[cursor.kind],
                        and_(
                            RecordEntry.kind == RecordKind.NOTE.value,
                            KIND_ORDER[RecordKind.NOTE] == KIND_ORDER[cursor.kind],
                            RecordEntry.id < cursor.source_id,
                        ),
                        KIND_ORDER[RecordKind.FOCUS] < KIND_ORDER[cursor.kind],
                        and_(
                            RecordEntry.kind == RecordKind.FOCUS.value,
                            KIND_ORDER[RecordKind.FOCUS] == KIND_ORDER[cursor.kind],
                            RecordEntry.id < cursor.source_id,
                        ),
                    ),
                ),
            )
        )
    entry_rows = db.scalars(
        entry_statement.order_by(entry_occurred_at.desc(), RecordEntry.id.desc()).limit(candidate_limit)
    ).all()

    book_occurred_at = func.coalesce(
        BookRecord.last_read_at,
        BookRecord.finished_at,
        BookRecord.updated_at,
        BookRecord.created_at,
    )
    book_statement = select(BookRecord, book_occurred_at.label("occurred_at")).where(
        BookRecord.is_in_shelf.is_(True)
    )
    if not is_admin:
        book_statement = book_statement.where(BookRecord.visibility == "public")
    book_statement = _apply_cursor(
        book_statement,
        book_occurred_at,
        BookRecord.id,
        RecordKind.READING,
        cursor,
    )
    book_rows = db.execute(
        book_statement.order_by(book_occurred_at.desc(), BookRecord.id.desc()).limit(candidate_limit)
    ).all()

    movie_occurred_at = func.coalesce(
        MovieRecord.watched_at,
        MovieRecord.updated_at,
        MovieRecord.created_at,
    )
    movie_statement = select(MovieRecord, movie_occurred_at.label("occurred_at"))
    if not is_admin:
        movie_statement = movie_statement.where(MovieRecord.visibility == "public")
    movie_statement = _apply_cursor(
        movie_statement,
        movie_occurred_at,
        MovieRecord.id,
        RecordKind.MOVIE,
        cursor,
    )
    movie_rows = db.execute(
        movie_statement.order_by(movie_occurred_at.desc(), MovieRecord.id.desc()).limit(candidate_limit)
    ).all()

    candidates: list[TimelineRecordOut] = [
        *[
            _note_to_timeline(entry) if entry.kind == RecordKind.NOTE.value else _focus_to_timeline(entry)
            for entry in entry_rows
            if (entry.note is not None if entry.kind == RecordKind.NOTE.value else entry.focus is not None)
        ],
        *[_book_to_timeline(record, occurred_at) for record, occurred_at in book_rows],
        *[_movie_to_timeline(record, occurred_at) for record, occurred_at in movie_rows],
    ]
    candidates.sort(key=_sort_key, reverse=True)

    has_more = len(candidates) > limit
    items = candidates[:limit]
    next_cursor = _encode_cursor(items[-1]) if has_more and items else None
    return TimelinePageOut(items=items, next_cursor=next_cursor, has_more=has_more)


def list_record_modules() -> list[RecordModuleOut]:
    return [
        RecordModuleOut(
            kind=RecordKind.NOTE,
            label="笔记",
            icon="notebook-pen",
            read_enabled=True,
            write_enabled=True,
            reason="公共记录表已接入",
        ),
        RecordModuleOut(
            kind=RecordKind.FOCUS,
            label="专注",
            icon="timer",
            read_enabled=True,
            write_enabled=True,
            reason="公共记录表已接入",
        ),
        RecordModuleOut(
            kind=RecordKind.READING,
            label="阅读",
            icon="book-open",
            read_enabled=True,
            write_enabled=True,
            reason="支持手动记录与微信读书同步",
        ),
        RecordModuleOut(
            kind=RecordKind.MOVIE,
            label="电影",
            icon="clapperboard",
            read_enabled=True,
            write_enabled=True,
            reason="支持手动记录",
        ),
    ]
