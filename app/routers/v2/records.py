from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_admin, get_current_user_optional
from app.models.user import User
from app.schemas.common import ResponseModel
from app.schemas.records_v2 import (
    FocusRecordCreate,
    MovieRecordCreate,
    NoteRecordCreate,
    ReadingRecordCreate,
    RecordModuleOut,
    TimelinePageOut,
    TimelineRecordOut,
)
from app.services.records import (
    InvalidTimelineCursor,
    create_focus_record,
    create_movie_record,
    create_note_record,
    create_reading_record,
    list_record_modules,
    list_timeline_records,
)


router = APIRouter(prefix="/records", tags=["记录 v2"])


@router.get("/modules", response_model=ResponseModel[list[RecordModuleOut]])
def get_record_modules() -> ResponseModel[list[RecordModuleOut]]:
    return ResponseModel(data=list_record_modules())


@router.get("/timeline", response_model=ResponseModel[TimelinePageOut])
def get_timeline(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
) -> ResponseModel[TimelinePageOut]:
    try:
        page = list_timeline_records(
            db,
            is_admin=bool(current_user and current_user.is_admin),
            limit=limit,
            cursor_value=cursor,
        )
    except InvalidTimelineCursor as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ResponseModel(data=page)


@router.post("/notes", response_model=ResponseModel[TimelineRecordOut], status_code=201)
def create_note(
    payload: NoteRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> ResponseModel[TimelineRecordOut]:
    return ResponseModel(data=create_note_record(db, owner_id=current_user.id, payload=payload))


@router.post("/focus", response_model=ResponseModel[TimelineRecordOut], status_code=201)
def create_focus(
    payload: FocusRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> ResponseModel[TimelineRecordOut]:
    return ResponseModel(data=create_focus_record(db, owner_id=current_user.id, payload=payload))


@router.post("/reading", response_model=ResponseModel[TimelineRecordOut], status_code=201)
def create_reading(
    payload: ReadingRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> ResponseModel[TimelineRecordOut]:
    return ResponseModel(data=create_reading_record(db, owner_id=current_user.id, payload=payload))


@router.post("/movies", response_model=ResponseModel[TimelineRecordOut], status_code=201)
def create_movie(
    payload: MovieRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
) -> ResponseModel[TimelineRecordOut]:
    return ResponseModel(data=create_movie_record(db, owner_id=current_user.id, payload=payload))
