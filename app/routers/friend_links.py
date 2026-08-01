from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_admin, require_public_interactions_enabled
from app.models.friend_link import FriendLink
from app.models.user import User
from app.schemas.common import ResponseModel
from app.schemas.friend_link import (
    FriendLinkAdmin as FriendLinkAdminSchema,
    FriendLinkApply,
    FriendLinkCreate,
    FriendLinkPublic,
    FriendLinkUpdate,
)
from app.utils.audit import record_admin_action


router = APIRouter(prefix="/friend-links", tags=["友链"])

ALLOWED_STATUSES = {"pending", "approved", "rejected", "offline"}


def _normalize_url(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw[:500]


def _sanitize_base(payload: FriendLinkApply | FriendLinkCreate | FriendLinkUpdate) -> dict:
    return {
        "name": payload.name.strip()[:100],
        "url": _normalize_url(payload.url),
        "logo": _normalize_url(payload.logo),
        "description": (payload.description or "").strip()[:255],
        "group_name": (payload.group_name or "推荐站点").strip()[:50] or "推荐站点",
        "contact": (payload.contact or "").strip()[:120],
        "reciprocal_url": _normalize_url(payload.reciprocal_url),
        "site_color": (payload.site_color or "").strip()[:20],
    }


def _ensure_unique_url(db: Session, url: str, exclude_id: Optional[int] = None) -> bool:
    query = db.query(FriendLink).filter(FriendLink.url == url)
    if exclude_id is not None:
        query = query.filter(FriendLink.id != exclude_id)
    return db.query(query.exists()).scalar() or False


def _status_rank():
    return case(
        (FriendLink.status == "pending", 0),
        (FriendLink.status == "approved", 1),
        (FriendLink.status == "offline", 2),
        else_=3,
    )


@router.get("", response_model=ResponseModel[List[FriendLinkPublic]])
def get_friend_links(
    group_name: Optional[str] = Query(None, description="按分组筛选"),
    db: Session = Depends(get_db),
):
    query = db.query(FriendLink).filter(FriendLink.status == "approved")
    if group_name:
        query = query.filter(FriendLink.group_name == group_name.strip())

    items = query.order_by(
        FriendLink.is_featured.desc(),
        FriendLink.sort_order.asc(),
        FriendLink.created_at.desc(),
    ).all()
    return ResponseModel(code=200, data=items)


@router.post("/apply", response_model=ResponseModel[FriendLinkAdminSchema])
def apply_friend_link(
    payload: FriendLinkApply,
    db: Session = Depends(get_db),
    _: None = Depends(require_public_interactions_enabled),
):
    data = _sanitize_base(payload)
    if not data["name"] or not data["url"]:
        return ResponseModel(code=400, msg="站点名称和链接不能为空")
    if _ensure_unique_url(db, data["url"]):
        return ResponseModel(code=409, msg="该站点已存在，请勿重复申请")

    item = FriendLink(
        **data,
        status="pending",
        sort_order=0,
        is_featured=False,
        review_note="",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return ResponseModel(code=200, msg="申请已提交，等待审核", data=item)


@router.get("/admin/list", response_model=ResponseModel[List[FriendLinkAdminSchema]])
def get_admin_friend_links(
    status: Optional[str] = Query(None, description="状态筛选"),
    keyword: Optional[str] = Query(None, description="关键词检索"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    query = db.query(FriendLink)

    if status:
        query = query.filter(FriendLink.status == status.strip().lower())

    if keyword:
        term = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                FriendLink.name.like(term),
                FriendLink.url.like(term),
                FriendLink.description.like(term),
                FriendLink.contact.like(term),
                FriendLink.group_name.like(term),
            )
        )

    items = query.order_by(
        _status_rank(),
        FriendLink.is_featured.desc(),
        FriendLink.sort_order.asc(),
        FriendLink.created_at.desc(),
    ).all()
    return ResponseModel(code=200, data=items)


@router.post("", response_model=ResponseModel[FriendLinkAdminSchema])
def create_friend_link(
    payload: FriendLinkCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    data = _sanitize_base(payload)
    status = (payload.status or "approved").strip().lower()
    if status not in ALLOWED_STATUSES:
        return ResponseModel(code=400, msg="友链状态不合法")
    if not data["name"] or not data["url"]:
        return ResponseModel(code=400, msg="站点名称和链接不能为空")
    if _ensure_unique_url(db, data["url"]):
        return ResponseModel(code=409, msg="该站点链接已存在")

    item = FriendLink(
        **data,
        sort_order=payload.sort_order,
        is_featured=payload.is_featured,
        status=status,
        review_note=(payload.review_note or "").strip()[:255],
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    record_admin_action(
        user=current_user,
        action="friend_link.create",
        target_type="friend_link",
        target_id=str(item.id),
        description=f"创建友链: {item.name}",
        request=request,
        extra={"status": item.status, "url": item.url},
    )
    return ResponseModel(code=200, msg="创建成功", data=item)


@router.put("/{id}", response_model=ResponseModel[FriendLinkAdminSchema])
def update_friend_link(
    id: int,
    payload: FriendLinkUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    item = db.query(FriendLink).filter(FriendLink.id == id).first()
    if not item:
        return ResponseModel(code=404, msg="友链不存在")

    data = _sanitize_base(payload)
    status = (payload.status or "pending").strip().lower()
    if status not in ALLOWED_STATUSES:
        return ResponseModel(code=400, msg="友链状态不合法")
    if not data["name"] or not data["url"]:
        return ResponseModel(code=400, msg="站点名称和链接不能为空")
    if _ensure_unique_url(db, data["url"], exclude_id=id):
        return ResponseModel(code=409, msg="该站点链接已存在")

    for key, value in data.items():
        setattr(item, key, value)
    item.sort_order = payload.sort_order
    item.is_featured = payload.is_featured
    item.status = status
    item.review_note = (payload.review_note or "").strip()[:255]

    db.commit()
    db.refresh(item)

    record_admin_action(
        user=current_user,
        action="friend_link.update",
        target_type="friend_link",
        target_id=str(item.id),
        description=f"更新友链: {item.name}",
        request=request,
        extra={"status": item.status, "url": item.url},
    )
    return ResponseModel(code=200, msg="更新成功", data=item)


@router.delete("/{id}", response_model=ResponseModel)
def delete_friend_link(
    id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    item = db.query(FriendLink).filter(FriendLink.id == id).first()
    if not item:
        return ResponseModel(code=404, msg="友链不存在")

    name = item.name
    db.delete(item)
    db.commit()

    record_admin_action(
        user=current_user,
        action="friend_link.delete",
        target_type="friend_link",
        target_id=str(id),
        description=f"删除友链: {name}",
        request=request,
    )
    return ResponseModel(code=200, msg="删除成功")
