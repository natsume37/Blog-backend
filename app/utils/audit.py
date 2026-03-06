import json
import logging
from typing import Any, Optional

from fastapi import Request

from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.user import User


logger = logging.getLogger(__name__)


def _get_client_ip(request: Optional[Request]) -> str:
    if not request:
        return ""
    header_candidates = [
        request.headers.get("x-forwarded-for"),
        request.headers.get("x-real-ip"),
        request.headers.get("cf-connecting-ip"),
    ]
    for value in header_candidates:
        if not value:
            continue
        first = value.split(",")[0].strip()
        if first and first.lower() != "unknown":
            return first
    return request.client.host if request.client else ""


def record_admin_action(
    *,
    user: Optional[User],
    action: str,
    target_type: str,
    target_id: Optional[str] = "",
    description: str = "",
    request: Optional[Request] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """Record audit log using an independent DB session to avoid business request failures."""
    db = SessionLocal()
    try:
        raw_extra = ""
        if extra:
            raw_extra = json.dumps(extra, ensure_ascii=False)[:4000]

        item = AuditLog(
            user_id=user.id if user else None,
            username=(user.username if user else "system")[:64],
            action=action[:64],
            target_type=target_type[:64],
            target_id=(target_id or "")[:64],
            description=description[:255],
            request_path=(request.url.path if request else "")[:255],
            request_method=(request.method if request else "")[:10],
            ip=_get_client_ip(request)[:50],
            user_agent=(request.headers.get("user-agent", "") if request else "")[:500],
            extra=raw_extra,
        )
        db.add(item)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("record_admin_action failed: %s", e)
    finally:
        db.close()
