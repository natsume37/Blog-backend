from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_admin
from app.models.tool_item import ToolItem
from app.models.user import User
from app.schemas.common import ResponseModel
from app.schemas.tool_item import (
    ToolItemAdmin as ToolItemAdminSchema,
    ToolItemCreate,
    ToolItemPublic,
    ToolItemUpdate,
)
from app.utils.audit import record_admin_action


router = APIRouter(prefix="/tools", tags=["工具墙"])

ALLOWED_STATUSES = {"draft", "published", "offline"}
ALLOWED_OPEN_MODES = {"new_tab", "same_tab"}
ALLOWED_TOOL_TYPES = {"website", "news", "navigation", "resource", "community", "internal", "other"}


def _normalize_url(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw[:500]


def _normalize_tags(value: Optional[str]) -> str:
    raw = (value or "").replace("，", ",").replace("\n", ",")
    items: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        cleaned = part.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(cleaned[:20])
    return ",".join(items)[:255]


def _sanitize_base(payload: ToolItemCreate | ToolItemUpdate) -> dict:
    tool_type = (payload.tool_type or "website").strip().lower() or "website"
    if tool_type not in ALLOWED_TOOL_TYPES:
        tool_type = "other"

    open_mode = (payload.open_mode or "new_tab").strip().lower() or "new_tab"
    if open_mode not in ALLOWED_OPEN_MODES:
        open_mode = "new_tab"

    return {
        "name": payload.name.strip()[:100],
        "url": _normalize_url(payload.url),
        "logo": _normalize_url(payload.logo),
        "description": (payload.description or "").strip()[:255],
        "category": (payload.category or "推荐工具").strip()[:50] or "推荐工具",
        "tool_type": tool_type,
        "badge": (payload.badge or "").strip()[:40],
        "tags": _normalize_tags(payload.tags),
        "site_color": (payload.site_color or "").strip()[:20],
        "subscription_url": _normalize_url(payload.subscription_url),
        "open_mode": open_mode,
    }


def _ensure_unique_url(db: Session, url: str, exclude_id: Optional[int] = None) -> bool:
    query = db.query(ToolItem).filter(ToolItem.url == url)
    if exclude_id is not None:
        query = query.filter(ToolItem.id != exclude_id)
    return db.query(query.exists()).scalar() or False


def _status_rank():
    return case(
        (ToolItem.status == "published", 0),
        (ToolItem.status == "draft", 1),
        else_=2,
    )


@router.get("", response_model=ResponseModel[List[ToolItemPublic]])
def get_tool_items(
    category: Optional[str] = Query(None, description="按分类筛选"),
    tool_type: Optional[str] = Query(None, description="按类型筛选"),
    keyword: Optional[str] = Query(None, description="关键词检索"),
    db: Session = Depends(get_db),
):
    query = db.query(ToolItem).filter(ToolItem.status == "published")
    if category:
        query = query.filter(ToolItem.category == category.strip())
    if tool_type:
        query = query.filter(ToolItem.tool_type == tool_type.strip().lower())
    if keyword:
        term = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                ToolItem.name.like(term),
                ToolItem.url.like(term),
                ToolItem.description.like(term),
                ToolItem.category.like(term),
                ToolItem.tags.like(term),
            )
        )

    items = query.order_by(
        ToolItem.is_featured.desc(),
        ToolItem.sort_order.asc(),
        ToolItem.created_at.desc(),
    ).all()
    return ResponseModel(code=200, data=items)


@router.get("/admin/list", response_model=ResponseModel[List[ToolItemAdminSchema]])
def get_admin_tool_items(
    status: Optional[str] = Query(None, description="状态筛选"),
    category: Optional[str] = Query(None, description="分类筛选"),
    tool_type: Optional[str] = Query(None, description="类型筛选"),
    keyword: Optional[str] = Query(None, description="关键词检索"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    query = db.query(ToolItem)

    if status:
        query = query.filter(ToolItem.status == status.strip().lower())

    if category:
        query = query.filter(ToolItem.category == category.strip())
    if tool_type:
        query = query.filter(ToolItem.tool_type == tool_type.strip().lower())

    if keyword:
        term = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                ToolItem.name.like(term),
                ToolItem.url.like(term),
                ToolItem.description.like(term),
                ToolItem.category.like(term),
                ToolItem.tags.like(term),
                ToolItem.badge.like(term),
            )
        )

    items = query.order_by(
        _status_rank(),
        ToolItem.is_featured.desc(),
        ToolItem.sort_order.asc(),
        ToolItem.created_at.desc(),
    ).all()
    return ResponseModel(code=200, data=items)


@router.post("", response_model=ResponseModel[ToolItemAdminSchema])
def create_tool_item(
    payload: ToolItemCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    data = _sanitize_base(payload)
    status = (payload.status or "published").strip().lower()
    if status not in ALLOWED_STATUSES:
        return ResponseModel(code=400, msg="工具状态不合法")
    if data["open_mode"] not in ALLOWED_OPEN_MODES:
        return ResponseModel(code=400, msg="打开方式不合法")
    if not data["name"] or not data["url"]:
        return ResponseModel(code=400, msg="工具名称和链接不能为空")
    if _ensure_unique_url(db, data["url"]):
        return ResponseModel(code=409, msg="该工具链接已存在")

    item = ToolItem(
        **data,
        sort_order=payload.sort_order,
        is_featured=payload.is_featured,
        status=status,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    record_admin_action(
        user=current_user,
        action="tool_item.create",
        target_type="tool_item",
        target_id=str(item.id),
        description=f"创建工具项: {item.name}",
        request=request,
        extra={"status": item.status, "url": item.url, "category": item.category},
    )
    return ResponseModel(code=200, msg="创建成功", data=item)


@router.put("/{id}", response_model=ResponseModel[ToolItemAdminSchema])
def update_tool_item(
    id: int,
    payload: ToolItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    item = db.query(ToolItem).filter(ToolItem.id == id).first()
    if not item:
        return ResponseModel(code=404, msg="工具项不存在")

    data = _sanitize_base(payload)
    status = (payload.status or "draft").strip().lower()
    if status not in ALLOWED_STATUSES:
        return ResponseModel(code=400, msg="工具状态不合法")
    if data["open_mode"] not in ALLOWED_OPEN_MODES:
        return ResponseModel(code=400, msg="打开方式不合法")
    if not data["name"] or not data["url"]:
        return ResponseModel(code=400, msg="工具名称和链接不能为空")
    if _ensure_unique_url(db, data["url"], exclude_id=id):
        return ResponseModel(code=409, msg="该工具链接已存在")

    for key, value in data.items():
        setattr(item, key, value)
    item.sort_order = payload.sort_order
    item.is_featured = payload.is_featured
    item.status = status

    db.commit()
    db.refresh(item)

    record_admin_action(
        user=current_user,
        action="tool_item.update",
        target_type="tool_item",
        target_id=str(item.id),
        description=f"更新工具项: {item.name}",
        request=request,
        extra={"status": item.status, "url": item.url, "category": item.category},
    )
    return ResponseModel(code=200, msg="更新成功", data=item)


@router.delete("/{id}", response_model=ResponseModel)
def delete_tool_item(
    id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    item = db.query(ToolItem).filter(ToolItem.id == id).first()
    if not item:
        return ResponseModel(code=404, msg="工具项不存在")

    name = item.name
    db.delete(item)
    db.commit()

    record_admin_action(
        user=current_user,
        action="tool_item.delete",
        target_type="tool_item",
        target_id=str(id),
        description=f"删除工具项: {name}",
        request=request,
    )
    return ResponseModel(code=200, msg="删除成功")
