from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Body, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user_optional, get_current_admin
from app.models.resource import Resource
from app.models.user import User
from app.schemas.resource import ResourceCreate, ResourceResponse, ResourceList, ResourceBatchDelete, ResourceSyncRequest
from app.schemas.common import ResponseModel, PagedData
from app.core.cache import RedisClient
from app.core.config import get_settings, Settings
from qiniu import Auth, BucketManager
from app.utils.audit import record_admin_action

router = APIRouter(prefix="/resources", tags=["资源管理"])


def _normalize_type(media_type: Optional[str]) -> Optional[str]:
    if not media_type:
        return None
    m = media_type.strip().lower()
    if m in {"image", "img"}:
        return "img"
    if m in {"video", "audio", "other"}:
        return m
    return m


def _guess_media_type(key: str, mime_type: Optional[str]) -> str:
    if mime_type:
        if mime_type.startswith("image/"):
            return "img"
        if mime_type.startswith("video/"):
            return "video"
        if mime_type.startswith("audio/"):
            return "audio"
    lower_key = (key or "").lower()
    if lower_key.startswith("img/"):
        return "img"
    if lower_key.startswith("video/"):
        return "video"
    if lower_key.startswith("audio/"):
        return "audio"
    return "other"

@router.post("", response_model=ResponseModel[ResourceResponse])
def create_resource(
    resource_in: ResourceCreate,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """记录新上传的资源"""
    # 检查key是否已存在
    existing = db.query(Resource).filter(Resource.key == resource_in.key).first()
    if existing:
        return ResponseModel(code=200, msg="Resource already exists", data=existing)
    
    new_resource = Resource(
        **resource_in.model_dump(),
        user_id=current_user.id if current_user else None
    )
    db.add(new_resource)
    db.commit()
    db.refresh(new_resource)
    
    # 清除资源列表缓存（通过递增版本号）
    # 这种方式可以瞬间让所有旧的列表缓存失效
    redis_client = RedisClient()
    redis_client.get_client().incr("resources:list:version")
    
    return ResponseModel(code=200, msg="Resource recorded", data=new_resource)

@router.get("", response_model=ResponseModel[PagedData[ResourceResponse]])
def get_resources(
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    type: Optional[str] = Query(None, description="media_type prefix, e.g. image, video"),
    keyword: Optional[str] = Query(None, description="按文件名或key模糊搜索"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings)
):
    """获取资源列表 (仅管理员)"""
    # 获取当前列表缓存版本号
    redis_client = RedisClient()
    version = redis_client.get_client().get("resources:list:version") or "1"
    
    # 缓存 Key (包含版本号)
    normalized_type = _normalize_type(type)
    cache_key = f"resources:list:v{version}:{current}:{size}:{normalized_type or 'all'}:{keyword or ''}"
    
    cached_data = redis_client.get(cache_key)
    if cached_data:
        return ResponseModel(code=200, data=PagedData(**cached_data))

    query = db.query(Resource)
    
    if normalized_type:
        query = query.filter(Resource.media_type == normalized_type)
    if keyword:
        query = query.filter(
            (Resource.filename.contains(keyword))
            | (Resource.key.contains(keyword))
        )
        
    total = query.count()
    items = query.order_by(Resource.created_at.desc()) \
        .offset((current - 1) * size) \
        .limit(size) \
        .all()
        
    result_data = PagedData(
        records=items,
        total=total,
        current=current,
        size=size
    )
    
    # 写入缓存
    json_compatible_items = [ResourceResponse.model_validate(item).model_dump(mode='json') for item in items]
    
    cache_value = {
        "records": json_compatible_items,
        "total": total,
        "current": current,
        "size": size
    }
    redis_client.set(cache_key, cache_value, expire=settings.REDIS_CACHE_TTL)

    return ResponseModel(
        code=200,
        data=result_data
    )

@router.delete("/{id}", response_model=ResponseModel)
def delete_resource(
    id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    """删除资源（同步删除七牛云文件）"""
    resource = db.query(Resource).filter(Resource.id == id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="资源不存在")
    
    # 1. 删除七牛云文件
    try:
        if settings.is_qiniu_enabled:
            q = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
            bucket = BucketManager(q)
            ret, info = bucket.delete(settings.QINIU_BUCKET, resource.key)
            # 即使七牛云返回错误（例如文件不存在），只要不是网络错误，我们都继续删除数据库记录
            if info.status_code != 200 and info.status_code != 612: # 612: file not found
                 # 记录日志但未必阻断
                 print(f"Failed to delete from Qiniu: {info}")
        else:
            print("Skipping Qiniu deletion (Configuration missing)")
    except Exception as e:
        print(f"Qiniu delete error: {e}")
        # 可选：如果硬性要求一致性，这里可以抛出异常

    # 2. 删除数据库记录
    target_key = resource.key
    db.delete(resource)
    db.commit()
    
    # 3. 清除相关缓存（版本号法）
    redis_client = RedisClient()
    redis_client.get_client().incr("resources:list:version")

    record_admin_action(
        user=current_user,
        action="resource.delete",
        target_type="resource",
        target_id=str(id),
        description=f"删除资源: {target_key}",
        request=request,
    )
    
    return ResponseModel(code=200, msg="删除成功")


@router.post("/admin/batch-delete", response_model=ResponseModel)
def batch_delete_resource(
    payload: ResourceBatchDelete,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    """批量删除资源（同步删除七牛云文件）"""
    if not payload.ids:
        return ResponseModel(code=400, msg="请选择资源")

    resources = db.query(Resource).filter(Resource.id.in_(payload.ids)).all()
    if not resources:
        return ResponseModel(code=404, msg="资源不存在")

    q = None
    bucket = None
    if settings.is_qiniu_enabled:
        q = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
        bucket = BucketManager(q)

    deleted = 0
    qiniu_failed = 0
    for resource in resources:
        if bucket:
            try:
                _ret, info = bucket.delete(settings.QINIU_BUCKET, resource.key)
                if info.status_code not in (200, 612):
                    qiniu_failed += 1
            except Exception:
                qiniu_failed += 1

        db.delete(resource)
        deleted += 1

    db.commit()

    redis_client = RedisClient()
    redis_client.get_client().incr("resources:list:version")

    record_admin_action(
        user=current_user,
        action="resource.batch_delete",
        target_type="resource",
        target_id=",".join(str(i) for i in payload.ids[:20]),
        description=f"批量删除资源 {deleted} 个",
        request=request,
        extra={"count": deleted, "qiniu_failed": qiniu_failed, "ids": payload.ids},
    )
    msg = f"批量删除完成，共 {deleted} 个"
    if qiniu_failed > 0:
        msg += f"，其中 {qiniu_failed} 个七牛删除失败"
    return ResponseModel(code=200, msg=msg, data={"deleted": deleted, "qiniu_failed": qiniu_failed})


@router.post("/admin/sync-qiniu", response_model=ResponseModel)
def sync_resources_from_qiniu(
    payload: ResourceSyncRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    """从七牛云同步对象到资源表（增量）"""
    if not settings.is_qiniu_enabled:
        return ResponseModel(code=400, msg="七牛云未配置，无法同步")

    limit = max(1, min(int(payload.limit or 1000), 3000))
    prefix = (payload.prefix or "").strip()

    q = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
    bucket = BucketManager(q)

    marker = ""
    created = 0
    updated = 0
    scanned = 0
    domain = settings.QINIU_DOMAIN.rstrip("/")

    while True:
        ret, eof, info = bucket.list(settings.QINIU_BUCKET, prefix=prefix or None, marker=marker, limit=min(1000, limit - scanned))
        if info.status_code != 200:
            return ResponseModel(code=500, msg=f"同步失败，七牛返回状态码: {info.status_code}")

        items = ret.get("items", []) if ret else []
        marker = ret.get("marker", "") if ret else ""
        for item in items:
            key = item.get("key", "")
            if not key:
                continue
            scanned += 1
            if scanned > limit:
                break

            fsize = int(item.get("fsize", 0) or 0)
            mime_type = item.get("mimeType") or None
            media_type = _guess_media_type(key, mime_type)
            base_url = f"{domain}/{key}"

            existing = db.query(Resource).filter(Resource.key == key).first()
            if existing:
                changed = False
                if existing.size != fsize:
                    existing.size = fsize
                    changed = True
                if existing.mime_type != mime_type:
                    existing.mime_type = mime_type
                    changed = True
                if existing.url != base_url:
                    existing.url = base_url
                    changed = True
                if existing.media_type != media_type:
                    existing.media_type = media_type
                    changed = True
                if changed:
                    updated += 1
            else:
                resource = Resource(
                    filename=key.split("/")[-1] or key,
                    key=key,
                    url=base_url,
                    media_type=media_type,
                    mime_type=mime_type,
                    size=fsize,
                    user_id=current_user.id,
                )
                db.add(resource)
                created += 1

        if scanned >= limit or eof or not marker:
            break

    db.commit()

    redis_client = RedisClient()
    redis_client.get_client().incr("resources:list:version")

    record_admin_action(
        user=current_user,
        action="resource.sync_qiniu",
        target_type="resource",
        target_id=prefix or "all",
        description=f"七牛云资源同步，扫描 {scanned}，新增 {created}，更新 {updated}",
        request=request,
        extra={"prefix": prefix, "limit": limit, "scanned": scanned, "created": created, "updated": updated},
    )

    return ResponseModel(
        code=200,
        msg=f"同步完成：扫描 {scanned}，新增 {created}，更新 {updated}",
        data={"scanned": scanned, "created": created, "updated": updated},
    )
