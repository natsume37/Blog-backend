from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_admin, get_current_user_optional
from app.models.record import BookRecord, MovieRecord, WeReadSyncState
from app.models.user import User
from app.schemas.common import ResponseModel
from app.schemas.record import (
    BookRecordDetailOut,
    BookRecordOut,
    BookRecordStatsOut,
    BookTimeStatsOut,
    MovieRecordOut,
    MovieRecordStatsOut,
    RecordVisibilityUpdateIn,
    WeReadSyncResult,
    WeReadSyncStatusOut,
)
from app.services.weread import (
    _seconds_to_duration,
    book_record_to_dict,
    book_time_stats_to_dict,
    sync_state_to_dict,
    sync_weread_records,
)
from app.utils.audit import record_admin_action

router = APIRouter(prefix="/records", tags=["记录"])


VISIBILITY_VALUES = {"public", "login", "private"}


def _normalize_visibility(value: str | None) -> str:
    normalized = (value or "public").strip().lower()
    if normalized not in VISIBILITY_VALUES:
        raise HTTPException(status_code=400, detail="可见性只能是 public/login/private")
    return normalized


def _can_view_visibility(visibility: str | None, current_user: User | None) -> bool:
    normalized = (visibility or "public").strip().lower()
    if current_user and current_user.is_admin:
        return True
    if normalized == "private":
        return False
    if normalized == "login":
        return current_user is not None
    return True


def _raise_visibility_denied(visibility: str | None) -> None:
    if (visibility or "public").strip().lower() == "login":
        raise HTTPException(status_code=401, detail="请先登录后查看记录")
    raise HTTPException(status_code=403, detail="记录仅管理员可见")


def _apply_visibility_filter(query, model, current_user: User | None):
    if current_user and current_user.is_admin:
        return query
    allowed = ["public", "login"] if current_user else ["public"]
    return query.filter(model.visibility.in_(allowed))


def _book_base_query(db: Session):
    return db.query(BookRecord).filter(
        BookRecord.source == "weread",
        BookRecord.is_in_shelf == True,
    )


def _visible_book_query(db: Session, current_user: User | None):
    return _apply_visibility_filter(_book_base_query(db), BookRecord, current_user)


def _all_book_records_visible(db: Session, current_user: User | None, visible_count: int) -> bool:
    if current_user and current_user.is_admin:
        return True
    return _book_base_query(db).count() == visible_count


def _visible_movie_query(db: Session, current_user: User | None):
    return _apply_visibility_filter(db.query(MovieRecord), MovieRecord, current_user)


def _loads_json_list(raw: str | None) -> list[str]:
    import json

    try:
        value = json.loads(raw or "[]")
        if isinstance(value, list):
            return [str(item) for item in value if str(item)]
    except Exception:
        pass
    return []


def _movie_duration(minutes: int | None) -> str:
    value = max(0, int(minutes or 0))
    return f"{value} min" if value else "0 min"


def _movie_record_to_dict(record: MovieRecord) -> dict:
    return {
        "id": record.id,
        "source_id": record.source_id,
        "title": record.title,
        "director": record.director or "",
        "cover": record.cover or "",
        "format": record.format or "",
        "status": record.status,
        "progress": record.progress or 0,
        "rating": round((record.rating or 0) / 10, 1) if record.rating else 0,
        "duration_minutes": record.duration_minutes or 0,
        "duration": _movie_duration(record.duration_minutes),
        "note": record.note or "",
        "tags": _loads_json_list(record.tags_json),
        "color": record.color or "#2f5d7c",
        "accent": record.accent or "#d6a35d",
        "visibility": record.visibility or "public",
        "is_top": bool(record.is_top),
        "watched_at": record.watched_at,
    }


@router.get("/books", response_model=ResponseModel[list[BookRecordOut]])
def get_book_records(
    status: Optional[str] = Query(None, description="阅读状态，如 阅读中/待读/已读完"),
    keyword: Optional[str] = Query(None, description="按书名、作者、分类、摘要搜索"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    query = _visible_book_query(db, current_user)
    if status and status != "全部":
        query = query.filter(BookRecord.status == status)
    if keyword:
        kw = keyword.strip()
        if kw:
            query = query.filter(
                (BookRecord.title.contains(kw))
                | (BookRecord.author.contains(kw))
                | (BookRecord.category.contains(kw))
                | (BookRecord.note_summary.contains(kw))
                | (BookRecord.tags_json.contains(kw))
            )

    records = query.order_by(BookRecord.is_top.desc(), BookRecord.last_read_at.desc(), BookRecord.updated_at.desc()).all()
    return ResponseModel(code=200, data=[book_record_to_dict(item) for item in records])


@router.get("/books/stats", response_model=ResponseModel[BookRecordStatsOut])
def get_book_record_stats(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    records = _visible_book_query(db, current_user).all()
    now = datetime.now()
    month_start = datetime(now.year, now.month, 1)

    total = len(records)
    finished = len([item for item in records if item.progress >= 100 or item.status == "已读完"])
    monthly_count = len([item for item in records if item.last_read_at and item.last_read_at >= month_start])
    note_count = sum(item.note_count or 0 for item in records)
    read_seconds = sum(item.read_seconds or 0 for item in records)
    rated = [item.rating for item in records if item.rating and item.rating > 0]
    average_rating = round((sum(rated) / len(rated)) / 10, 1) if rated else 0

    state = db.query(WeReadSyncState).filter(WeReadSyncState.key == "weread").first()
    can_use_global_stats = _all_book_records_visible(db, current_user, total)
    time_stats = book_time_stats_to_dict(state if can_use_global_stats else None, records)
    if read_seconds <= 0:
        read_seconds = time_stats["total_read_seconds"]
    data = BookRecordStatsOut(
        total=total,
        monthly_count=monthly_count,
        completion_rate=round((finished / total) * 100) if total else 0,
        note_count=note_count,
        average_rating=average_rating,
        read_seconds=read_seconds,
        read_duration=_seconds_to_duration(read_seconds),
        last_sync_at=state.last_success_at if state else None,
    )
    return ResponseModel(code=200, data=data)


@router.get("/books/time-stats", response_model=ResponseModel[BookTimeStatsOut])
def get_book_time_stats(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    records = _visible_book_query(db, current_user).all()
    state = db.query(WeReadSyncState).filter(WeReadSyncState.key == "weread").first()
    if not _all_book_records_visible(db, current_user, len(records)):
        state = None
    return ResponseModel(code=200, data=BookTimeStatsOut(**book_time_stats_to_dict(state, records)))


@router.get("/books/{id}", response_model=ResponseModel[BookRecordDetailOut])
def get_book_record_detail(
    id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    record = _book_base_query(db).filter(BookRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="读书记录不存在")
    if not _can_view_visibility(record.visibility, current_user):
        _raise_visibility_denied(record.visibility)
    return ResponseModel(code=200, data=book_record_to_dict(record, include_notes=True))


@router.get("/movies", response_model=ResponseModel[list[MovieRecordOut]])
def get_movie_records(
    status: Optional[str] = Query(None, description="观影状态，如 已看完/想看/重看中"),
    keyword: Optional[str] = Query(None, description="按片名、导演、标签、笔记搜索"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    query = _visible_movie_query(db, current_user)
    if status and status != "全部":
        query = query.filter(MovieRecord.status == status)
    if keyword:
        kw = keyword.strip()
        if kw:
            query = query.filter(
                (MovieRecord.title.contains(kw))
                | (MovieRecord.director.contains(kw))
                | (MovieRecord.note.contains(kw))
                | (MovieRecord.tags_json.contains(kw))
            )

    records = query.order_by(MovieRecord.is_top.desc(), MovieRecord.watched_at.desc(), MovieRecord.updated_at.desc()).all()
    return ResponseModel(code=200, data=[_movie_record_to_dict(item) for item in records])


@router.get("/movies/stats", response_model=ResponseModel[MovieRecordStatsOut])
def get_movie_record_stats(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    records = _visible_movie_query(db, current_user).all()
    now = datetime.now()
    month_start = datetime(now.year, now.month, 1)
    rated = [item.rating for item in records if item.rating and item.rating > 0]
    total_duration_minutes = sum(item.duration_minutes or 0 for item in records)
    data = MovieRecordStatsOut(
        total=len(records),
        monthly_count=len([item for item in records if item.watched_at and item.watched_at >= month_start]),
        finished_count=len([item for item in records if item.progress >= 100 or item.status == "已看完"]),
        average_rating=round((sum(rated) / len(rated)) / 10, 1) if rated else 0,
        total_duration_minutes=total_duration_minutes,
        total_duration=_movie_duration(total_duration_minutes),
    )
    return ResponseModel(code=200, data=data)


@router.get("/movies/{id}", response_model=ResponseModel[MovieRecordOut])
def get_movie_record_detail(
    id: int,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    record = db.query(MovieRecord).filter(MovieRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="电影记录不存在")
    if not _can_view_visibility(record.visibility, current_user):
        _raise_visibility_denied(record.visibility)
    return ResponseModel(code=200, data=_movie_record_to_dict(record))


@router.get("/admin/books", response_model=ResponseModel[list[BookRecordOut]])
def get_admin_book_records(
    status: Optional[str] = Query(None, description="阅读状态"),
    keyword: Optional[str] = Query(None, description="按书名、作者、分类、摘要搜索"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_admin),
):
    query = _book_base_query(db)
    if status and status != "全部":
        query = query.filter(BookRecord.status == status)
    if keyword:
        kw = keyword.strip()
        if kw:
            query = query.filter(
                (BookRecord.title.contains(kw))
                | (BookRecord.author.contains(kw))
                | (BookRecord.category.contains(kw))
                | (BookRecord.note_summary.contains(kw))
                | (BookRecord.tags_json.contains(kw))
            )
    records = query.order_by(BookRecord.is_top.desc(), BookRecord.last_read_at.desc(), BookRecord.updated_at.desc()).all()
    return ResponseModel(code=200, data=[book_record_to_dict(item) for item in records])


@router.patch("/admin/books/{id}/visibility", response_model=ResponseModel[BookRecordOut])
def update_book_record_visibility(
    id: int,
    payload: RecordVisibilityUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    record = _book_base_query(db).filter(BookRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="读书记录不存在")
    record.visibility = _normalize_visibility(payload.visibility)
    db.commit()
    db.refresh(record)
    record_admin_action(
        user=current_user,
        action="records.book.visibility",
        target_type="book_record",
        target_id=str(record.id),
        description=f"更新读书记录可见性: {record.title} -> {record.visibility}",
        request=request,
    )
    return ResponseModel(code=200, msg="可见性已更新", data=book_record_to_dict(record))


@router.get("/admin/movies", response_model=ResponseModel[list[MovieRecordOut]])
def get_admin_movie_records(
    status: Optional[str] = Query(None, description="观影状态"),
    keyword: Optional[str] = Query(None, description="按片名、导演、标签、笔记搜索"),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_admin),
):
    query = db.query(MovieRecord)
    if status and status != "全部":
        query = query.filter(MovieRecord.status == status)
    if keyword:
        kw = keyword.strip()
        if kw:
            query = query.filter(
                (MovieRecord.title.contains(kw))
                | (MovieRecord.director.contains(kw))
                | (MovieRecord.note.contains(kw))
                | (MovieRecord.tags_json.contains(kw))
            )
    records = query.order_by(MovieRecord.is_top.desc(), MovieRecord.watched_at.desc(), MovieRecord.updated_at.desc()).all()
    return ResponseModel(code=200, data=[_movie_record_to_dict(item) for item in records])


@router.patch("/admin/movies/{id}/visibility", response_model=ResponseModel[MovieRecordOut])
def update_movie_record_visibility(
    id: int,
    payload: RecordVisibilityUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    record = db.query(MovieRecord).filter(MovieRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="电影记录不存在")
    record.visibility = _normalize_visibility(payload.visibility)
    db.commit()
    db.refresh(record)
    record_admin_action(
        user=current_user,
        action="records.movie.visibility",
        target_type="movie_record",
        target_id=str(record.id),
        description=f"更新电影记录可见性: {record.title} -> {record.visibility}",
        request=request,
    )
    return ResponseModel(code=200, msg="可见性已更新", data=_movie_record_to_dict(record))


@router.post("/weread/sync", response_model=ResponseModel[WeReadSyncResult])
def sync_weread(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    result = sync_weread_records(db, settings, force_notes=True)
    record_admin_action(
        user=current_user,
        action="records.weread.sync",
        target_type="weread",
        target_id="global",
        description=f"手动同步微信读书: {result.status}",
        request=request,
        extra={
            "books_synced": result.books_synced,
            "notes_synced": result.notes_synced,
            "skipped": result.skipped,
        },
    )
    return ResponseModel(code=200, msg=result.message, data=WeReadSyncResult(**result.__dict__))


@router.get("/weread/status", response_model=ResponseModel[WeReadSyncStatusOut])
def get_weread_sync_status(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_admin),
):
    state = db.query(WeReadSyncState).filter(WeReadSyncState.key == "weread").first()
    return ResponseModel(code=200, data=WeReadSyncStatusOut(**sync_state_to_dict(state, settings)))
