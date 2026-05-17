import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base
from app.models.record import BookRecord, MovieRecord
from app.routers import records


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _user(is_admin: bool = False):
    return SimpleNamespace(is_admin=is_admin)


def test_book_visibility_filter_respects_viewer_role() -> None:
    db = _session()
    db.add_all([
        BookRecord(source="weread", source_id="book-public", title="Public", is_in_shelf=True, visibility="public"),
        BookRecord(source="weread", source_id="book-login", title="Login", is_in_shelf=True, visibility="login"),
        BookRecord(source="weread", source_id="book-private", title="Private", is_in_shelf=True, visibility="private", is_private=True),
    ])
    db.commit()

    anonymous = records._visible_book_query(db, None).order_by(BookRecord.source_id).all()
    logged_in = records._visible_book_query(db, _user()).order_by(BookRecord.source_id).all()
    admin = records._visible_book_query(db, _user(is_admin=True)).order_by(BookRecord.source_id).all()

    assert [item.source_id for item in anonymous] == ["book-public"]
    assert [item.source_id for item in logged_in] == ["book-login", "book-public"]
    assert [item.source_id for item in admin] == ["book-login", "book-private", "book-public"]


def test_movie_visibility_filter_respects_viewer_role() -> None:
    db = _session()
    db.add_all([
        MovieRecord(source_id="movie-public", title="Public", visibility="public"),
        MovieRecord(source_id="movie-login", title="Login", visibility="login"),
        MovieRecord(source_id="movie-private", title="Private", visibility="private"),
    ])
    db.commit()

    anonymous = records._visible_movie_query(db, None).order_by(MovieRecord.source_id).all()
    logged_in = records._visible_movie_query(db, _user()).order_by(MovieRecord.source_id).all()
    admin = records._visible_movie_query(db, _user(is_admin=True)).order_by(MovieRecord.source_id).all()

    assert [item.source_id for item in anonymous] == ["movie-public"]
    assert [item.source_id for item in logged_in] == ["movie-login", "movie-public"]
    assert [item.source_id for item in admin] == ["movie-login", "movie-private", "movie-public"]


def test_global_book_stats_only_used_when_current_viewer_can_see_every_book() -> None:
    db = _session()
    db.add_all([
        BookRecord(source="weread", source_id="book-public", title="Public", is_in_shelf=True, visibility="public"),
        BookRecord(source="weread", source_id="book-login", title="Login", is_in_shelf=True, visibility="login"),
        BookRecord(source="weread", source_id="book-private", title="Private", is_in_shelf=True, visibility="private", is_private=True),
    ])
    db.commit()

    anonymous_count = records._visible_book_query(db, None).count()
    logged_in_count = records._visible_book_query(db, _user()).count()
    admin_count = records._visible_book_query(db, _user(is_admin=True)).count()

    assert records._all_book_records_visible(db, None, anonymous_count) is False
    assert records._all_book_records_visible(db, _user(), logged_in_count) is False
    assert records._all_book_records_visible(db, _user(is_admin=True), admin_count) is True


def test_invalid_record_visibility_is_rejected() -> None:
    try:
        records._normalize_visibility("team-only")
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("invalid visibility should be rejected")


def test_missing_visibility_defaults_to_admin_only() -> None:
    assert records._normalize_visibility(None) == "private"
    assert records._can_view_visibility(None, None) is False
    assert records._can_view_visibility(None, _user(is_admin=True)) is True
