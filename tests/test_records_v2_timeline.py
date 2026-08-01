from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.user import User
from app.models.record import BookRecord, MovieRecord
from app.schemas.records_v2 import (
    FocusRecordCreate,
    MovieRecordCreate,
    NoteRecordCreate,
    ReadingRecordCreate,
    RecordKind,
)
from app.services.records.timeline import (
    InvalidTimelineCursor,
    list_record_modules,
    list_timeline_records,
)
from app.services.records import (
    create_focus_record,
    create_movie_record,
    create_note_record,
    create_reading_record,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def _seed_records(db) -> None:
    now = datetime(2026, 8, 1, 12, 0, 0)
    db.add_all(
        [
            BookRecord(
                source="weread",
                source_id="book-public",
                title="公开书籍",
                author="作者甲",
                progress=42,
                read_seconds=1800,
                status="阅读中",
                visibility="public",
                is_in_shelf=True,
                last_read_at=now,
            ),
            BookRecord(
                source="weread",
                source_id="book-private",
                title="私有书籍",
                visibility="private",
                is_in_shelf=True,
                last_read_at=now - timedelta(hours=2),
            ),
            MovieRecord(
                source_id="movie-public",
                title="公开电影",
                director="导演甲",
                status="看过",
                rating=45,
                visibility="public",
                watched_at=now - timedelta(hours=1),
            ),
            MovieRecord(
                source_id="movie-private",
                title="私有电影",
                visibility="private",
                watched_at=now - timedelta(hours=3),
            ),
        ]
    )
    db.commit()


def test_public_timeline_only_returns_public_records() -> None:
    db = _session()
    _seed_records(db)

    page = list_timeline_records(db, is_admin=False)

    assert [item.title for item in page.items] == ["《公开书籍》读到 42%", "《公开电影》"]
    assert [item.kind for item in page.items] == [RecordKind.READING, RecordKind.MOVIE]
    assert page.items[1].detail.rating == 4.5
    assert page.has_more is False


def test_admin_timeline_includes_private_records() -> None:
    db = _session()
    _seed_records(db)

    page = list_timeline_records(db, is_admin=True)

    assert len(page.items) == 4
    assert {item.visibility.value for item in page.items} == {"public", "private"}


def test_timeline_cursor_is_stable_across_record_types() -> None:
    db = _session()
    _seed_records(db)

    first_page = list_timeline_records(db, is_admin=True, limit=2)
    second_page = list_timeline_records(
        db,
        is_admin=True,
        limit=2,
        cursor_value=first_page.next_cursor,
    )

    assert first_page.has_more is True
    assert first_page.next_cursor
    assert second_page.has_more is False
    assert {item.id for item in first_page.items}.isdisjoint(item.id for item in second_page.items)
    assert len(first_page.items) + len(second_page.items) == 4


def test_invalid_timeline_cursor_is_rejected() -> None:
    db = _session()

    with pytest.raises(InvalidTimelineCursor):
        list_timeline_records(db, is_admin=False, cursor_value="not-a-cursor")


def test_module_registry_exposes_enabled_record_modules() -> None:
    modules = {module.kind: module for module in list_record_modules()}

    assert modules[RecordKind.READING].read_enabled is True
    assert modules[RecordKind.MOVIE].read_enabled is True
    assert modules[RecordKind.NOTE].read_enabled is True
    assert modules[RecordKind.NOTE].write_enabled is True
    assert modules[RecordKind.FOCUS].read_enabled is True
    assert modules[RecordKind.FOCUS].write_enabled is True


def test_modular_record_commands_share_one_timeline() -> None:
    db = _session()
    owner = User(
        username="owner",
        email="owner@example.com",
        hashed_password="test",
        is_admin=True,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    create_note_record(
        db,
        owner_id=owner.id,
        payload=NoteRecordCreate(content="记录一个想法", visibility="public", tags=["设计"]),
    )
    create_focus_record(
        db,
        owner_id=owner.id,
        payload=FocusRecordCreate(task="整理时间流", duration_seconds=1500, target_seconds=2700),
    )
    create_reading_record(
        db,
        owner_id=owner.id,
        payload=ReadingRecordCreate(book_title="设计中的设计", progress=42, duration_minutes=30),
    )
    create_movie_record(
        db,
        owner_id=owner.id,
        payload=MovieRecordCreate(movie_title="银翼杀手", rating=4.5, status="看过"),
    )

    admin_page = list_timeline_records(db, is_admin=True)
    assert {item.kind for item in admin_page.items} == set(RecordKind)
    assert admin_page.items[0].kind == RecordKind.MOVIE  # 最后写入的记录时间最新

    public_page = list_timeline_records(db, is_admin=False)
    assert [item.kind for item in public_page.items] == [RecordKind.NOTE]
    assert public_page.items[0].tags == ["设计"]


def test_record_command_source_key_is_idempotent() -> None:
    db = _session()
    owner = User(
        username="idempotent-owner",
        email="idempotent@example.com",
        hashed_password="test",
        is_admin=True,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)

    payload = NoteRecordCreate(
        content="只创建一次",
        source_key="offline-note-1",
    )
    first = create_note_record(db, owner_id=owner.id, payload=payload)
    second = create_note_record(db, owner_id=owner.id, payload=payload)

    assert first.id == second.id
    assert len(list_timeline_records(db, is_admin=True).items) == 1
