from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_admin
from app.models.record import BookRecord, WeReadSyncState
from app.models.user import User
from app.schemas.common import ResponseModel
from app.schemas.record import (
    BookRecordDetailOut,
    BookRecordOut,
    BookRecordStatsOut,
    BookTimeStatsOut,
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


def _public_book_query(db: Session):
    return db.query(BookRecord).filter(
        BookRecord.source == "weread",
        BookRecord.is_in_shelf == True,
        BookRecord.is_private == False,
    )


@router.get("/books", response_model=ResponseModel[list[BookRecordOut]])
def get_book_records(
    status: Optional[str] = Query(None, description="阅读状态，如 阅读中/待读/已读完"),
    keyword: Optional[str] = Query(None, description="按书名、作者、分类、摘要搜索"),
    db: Session = Depends(get_db),
):
    query = _public_book_query(db)
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
def get_book_record_stats(db: Session = Depends(get_db)):
    records = _public_book_query(db).all()
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
    time_stats = book_time_stats_to_dict(state, records)
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
def get_book_time_stats(db: Session = Depends(get_db)):
    records = _public_book_query(db).all()
    state = db.query(WeReadSyncState).filter(WeReadSyncState.key == "weread").first()
    return ResponseModel(code=200, data=BookTimeStatsOut(**book_time_stats_to_dict(state, records)))


@router.get("/books/{id}", response_model=ResponseModel[BookRecordDetailOut])
def get_book_record_detail(id: int, db: Session = Depends(get_db)):
    record = _public_book_query(db).filter(BookRecord.id == id).first()
    if not record:
        raise HTTPException(status_code=404, detail="读书记录不存在")
    return ResponseModel(code=200, data=book_record_to_dict(record, include_notes=True))


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
