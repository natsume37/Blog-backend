from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_admin
from app.models.login_log import LoginLog
from app.models.user import User
from app.schemas.common import ResponseModel, PagedData
from app.schemas.login_log import LoginLogItem


router = APIRouter(prefix="/login-logs", tags=["登录日志"])


@router.get("/admin/list", response_model=ResponseModel[PagedData[LoginLogItem]])
def get_login_logs(
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    success: Optional[bool] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    query = db.query(LoginLog)
    if success is not None:
        query = query.filter(LoginLog.success == success)
    if keyword:
        query = query.filter(
            (LoginLog.username.contains(keyword))
            | (LoginLog.ip.contains(keyword))
            | (LoginLog.reason.contains(keyword))
        )
    query = query.order_by(LoginLog.created_at.desc(), LoginLog.id.desc())
    total = query.count()
    rows = query.offset((current - 1) * size).limit(size).all()
    return ResponseModel(
        code=200,
        data=PagedData(
            records=[LoginLogItem.model_validate(item) for item in rows],
            total=total,
            current=current,
            size=size,
        ),
    )
