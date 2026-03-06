from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_admin
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogItem
from app.schemas.common import PagedData, ResponseModel


router = APIRouter(prefix="/audit-logs", tags=["审计日志"])


@router.get("/admin/list", response_model=ResponseModel[PagedData[AuditLogItem]])
def get_audit_logs(
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    query = db.query(AuditLog)

    if action:
        query = query.filter(AuditLog.action == action)
    if target_type:
        query = query.filter(AuditLog.target_type == target_type)
    if keyword:
        query = query.filter(
            (AuditLog.description.contains(keyword))
            | (AuditLog.username.contains(keyword))
            | (AuditLog.target_id.contains(keyword))
        )

    query = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    total = query.count()
    records = query.offset((current - 1) * size).limit(size).all()

    return ResponseModel(
        code=200,
        data=PagedData(
            records=[AuditLogItem.model_validate(item) for item in records],
            total=total,
            current=current,
            size=size,
        ),
    )
