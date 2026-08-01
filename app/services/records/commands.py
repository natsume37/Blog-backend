"""记录模块的写入用例。

写入统一先创建 ``record_entries``，再写入模块详情表，保证时间流公共字段和
模块字段始终在同一个事务中落库。阅读、电影仍保留旧表，方便现有同步能力继续工作。
"""

import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.record import BookRecord, MovieRecord
from app.models.record_core import FocusSession, NoteRecord, RecordEntry, RecordTag
from app.schemas.records_v2 import (
    FocusRecordCreate,
    FocusTimelineRecord,
    MovieRecordCreate,
    MovieTimelineRecord,
    NoteRecordCreate,
    NoteTimelineRecord,
    ReadingRecordCreate,
    ReadingTimelineRecord,
    RecordKind,
)
from app.services.records.timeline import (
    _book_to_timeline,
    _focus_to_timeline,
    _movie_to_timeline,
    _note_to_timeline,
)


def _now() -> datetime:
    """统一使用无时区 UTC，和现有记录表的 DateTime 保持一致。"""

    return datetime.now(timezone.utc).replace(tzinfo=None)


def _database_time(value: datetime | None) -> datetime | None:
    """将带时区输入转为数据库统一使用的无时区 UTC。"""

    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _commit(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def _clean_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        value = tag.strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value[:80])
    return result


def _slugify(value: str) -> str:
    return "-".join(value.lower().split())[:100] or "tag"


def _attach_tags(db: Session, entry: RecordEntry, owner_id: int, tags: list[str]) -> None:
    """按站主复用标签，避免模块之间产生重复标签。"""

    for name in _clean_tags(tags):
        tag = db.scalar(
            select(RecordTag).where(
                RecordTag.owner_id == owner_id,
                RecordTag.name == name,
            )
        )
        if tag is None:
            tag = RecordTag(owner_id=owner_id, name=name, slug=_slugify(name))
            db.add(tag)
            db.flush()
        entry.tags.append(tag)


def _entry(
    *,
    owner_id: int,
    kind: RecordKind,
    title: str,
    summary: str,
    visibility: str,
    occurred_at: datetime,
    source_key: str | None,
) -> RecordEntry:
    return RecordEntry(
        owner_id=owner_id,
        kind=kind.value,
        title=title.strip(),
        summary=summary.strip(),
        visibility=visibility,
        status="active",
        occurred_at=occurred_at,
        source="manual",
        source_key=source_key or uuid4().hex,
    )


def _existing_entry(db: Session, *, owner_id: int, kind: RecordKind, source_key: str | None) -> RecordEntry | None:
    if not source_key:
        return None
    return db.scalar(
        select(RecordEntry).where(
            RecordEntry.owner_id == owner_id,
            RecordEntry.kind == kind.value,
            RecordEntry.source == "manual",
            RecordEntry.source_key == source_key,
        )
    )


def create_note_record(db: Session, *, owner_id: int, payload: NoteRecordCreate) -> NoteTimelineRecord:
    existing = _existing_entry(db, owner_id=owner_id, kind=RecordKind.NOTE, source_key=payload.source_key)
    if existing is not None:
        return _note_to_timeline(existing)
    occurred_at = _database_time(payload.occurred_at) or _now()
    entry = _entry(
        owner_id=owner_id,
        kind=RecordKind.NOTE,
        title=payload.content.strip().splitlines()[0][:80],
        summary=payload.content,
        visibility=payload.visibility.value,
        occurred_at=occurred_at,
        source_key=payload.source_key,
    )
    entry.note = NoteRecord(content=payload.content.strip(), format=payload.format)
    db.add(entry)
    _attach_tags(db, entry, owner_id, payload.tags)
    _commit(db)
    db.refresh(entry)
    return _note_to_timeline(entry, occurred_at)


def create_focus_record(db: Session, *, owner_id: int, payload: FocusRecordCreate) -> FocusTimelineRecord:
    existing = _existing_entry(db, owner_id=owner_id, kind=RecordKind.FOCUS, source_key=payload.source_key)
    if existing is not None:
        return _focus_to_timeline(existing)
    now = _now()
    started_at = _database_time(payload.started_at) or now
    ended_at = _database_time(payload.ended_at)
    occurred_at = _database_time(payload.occurred_at) or ended_at or started_at
    entry = _entry(
        owner_id=owner_id,
        kind=RecordKind.FOCUS,
        title=payload.task,
        summary=payload.project,
        visibility="private",
        occurred_at=occurred_at,
        source_key=payload.source_key,
    )
    entry.focus = FocusSession(
        task=payload.task.strip(),
        project=payload.project.strip() or None,
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=payload.duration_seconds,
        target_seconds=payload.target_seconds,
        source="manual",
    )
    db.add(entry)
    _attach_tags(db, entry, owner_id, payload.tags)
    _commit(db)
    db.refresh(entry)
    return _focus_to_timeline(entry, occurred_at)


def _reading_status(value: str) -> str:
    return {"想读": "待读", "在读": "阅读中", "读完": "已读完"}.get(value, value)


def create_reading_record(
    db: Session,
    *,
    owner_id: int,
    payload: ReadingRecordCreate,
) -> ReadingTimelineRecord:
    existing = _existing_entry(db, owner_id=owner_id, kind=RecordKind.READING, source_key=payload.source_key)
    if existing is not None:
        if existing.book is None:
            raise ValueError(f"阅读记录 {existing.id} 缺少详情")
        return _book_to_timeline(existing.book, existing.occurred_at)
    occurred_at = _database_time(payload.occurred_at) or _now()
    status = _reading_status(payload.status)
    entry = _entry(
        owner_id=owner_id,
        kind=RecordKind.READING,
        title=payload.book_title,
        summary=payload.note or payload.author,
        visibility=payload.visibility.value,
        occurred_at=occurred_at,
        source_key=payload.source_key,
    )
    book = BookRecord(
        source="manual",
        source_id=f"manual-{uuid4().hex}",
        title=payload.book_title.strip(),
        author=payload.author.strip(),
        progress=payload.progress,
        read_seconds=payload.duration_minutes * 60,
        status=status,
        note_summary=payload.note.strip(),
        tags_json=json.dumps(_clean_tags(payload.tags), ensure_ascii=False),
        visibility=payload.visibility.value,
        is_private=payload.visibility.value != "public",
        is_in_shelf=True,
        last_read_at=occurred_at,
        finished_at=occurred_at if payload.progress >= 100 else None,
    )
    entry.book = book
    db.add(entry)
    _attach_tags(db, entry, owner_id, payload.tags)
    _commit(db)
    db.refresh(book)
    return _book_to_timeline(book, occurred_at)


def _movie_status(value: str) -> str:
    return {"想看": "想看", "在看": "在看", "看过": "已看完"}.get(value, value)


def create_movie_record(
    db: Session,
    *,
    owner_id: int,
    payload: MovieRecordCreate,
) -> MovieTimelineRecord:
    existing = _existing_entry(db, owner_id=owner_id, kind=RecordKind.MOVIE, source_key=payload.source_key)
    if existing is not None:
        if existing.movie is None:
            raise ValueError(f"电影记录 {existing.id} 缺少详情")
        return _movie_to_timeline(existing.movie, existing.occurred_at)
    occurred_at = _database_time(payload.occurred_at) or _now()
    status = _movie_status(payload.status)
    entry = _entry(
        owner_id=owner_id,
        kind=RecordKind.MOVIE,
        title=payload.movie_title,
        summary=payload.note or payload.director,
        visibility=payload.visibility.value,
        occurred_at=occurred_at,
        source_key=payload.source_key,
    )
    movie = MovieRecord(
        source="manual",
        source_id=f"manual-{uuid4().hex}",
        title=payload.movie_title.strip(),
        director=payload.director.strip(),
        rating=round(payload.rating * 10),
        status=status,
        duration_minutes=payload.duration_minutes,
        note=payload.note.strip(),
        tags_json=json.dumps(_clean_tags(payload.tags), ensure_ascii=False),
        visibility=payload.visibility.value,
        watched_at=occurred_at if status == "已看完" else None,
    )
    entry.movie = movie
    db.add(entry)
    _attach_tags(db, entry, owner_id, payload.tags)
    _commit(db)
    db.refresh(movie)
    return _movie_to_timeline(movie, occurred_at)


__all__ = [
    "create_focus_record",
    "create_movie_record",
    "create_note_record",
    "create_reading_record",
]
