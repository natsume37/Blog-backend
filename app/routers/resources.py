from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Body, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user_optional, get_current_admin
from app.models.resource import Resource
from app.models.article import Article
from app.models.user import User
from app.schemas.resource import (
    ResourceCreate,
    ResourceResponse,
    ResourceList,
    ResourceBatchDelete,
    ResourceSyncRequest,
    ResourceReferences,
    ResourceArticleRef,
)
from app.schemas.common import ResponseModel, PagedData
from app.core.cache import RedisClient
from app.core.config import get_settings, Settings
from app.services.resource_qiniu import delete_qiniu_resources, sync_qiniu_resources
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


def _find_referenced_articles(db: Session, key: str, url: str):
    return (
        db.query(Article)
        .filter(
            (Article.content.contains(key))
            | (Article.cover.contains(key))
            | (Article.content.contains(url))
            | (Article.cover.contains(url))
        )
        .limit(50)
        .all()
    )

@router.post("", response_model=ResponseModel[ResourceResponse])
def create_resource(
    resource_in: ResourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """记录新上传的资源"""
    # 检查key是否已存在
    existing = db.query(Resource).filter(Resource.key == resource_in.key).first()
    if existing:
        return ResponseModel(code=200, msg="Resource already exists", data=existing)
    
    new_resource = Resource(
        **resource_in.model_dump(),
        user_id=current_user.id,
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
    force: bool = Query(False, description="是否强制删除（忽略引用关系）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    """删除资源（同步删除七牛云文件）"""
    resource = db.query(Resource).filter(Resource.id == id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="资源不存在")

    refs = _find_referenced_articles(db, resource.key, resource.url)
    if refs and not force:
        return ResponseModel(
            code=409,
            msg=f"资源正在被 {len(refs)} 篇文章引用，请先替换引用后再删，或使用强制删除。",
            data={
                "ref_count": len(refs),
                "articles": [{"id": a.id, "title": a.title} for a in refs[:10]],
            },
        )
    
    # 1. 删除七牛云文件
    delete_qiniu_resources([resource.key], settings)

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

    deleted = 0
    skipped_refs: list[dict] = []
    pending_qiniu_keys: list[str] = []
    for resource in resources:
        refs = _find_referenced_articles(db, resource.key, resource.url)
        if refs and not payload.force:
            skipped_refs.append({
                "id": resource.id,
                "key": resource.key,
                "ref_count": len(refs),
            })
            continue

        pending_qiniu_keys.append(resource.key)
        db.delete(resource)
        deleted += 1

    qiniu_failed = delete_qiniu_resources(pending_qiniu_keys, settings)
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
        extra={
            "count": deleted,
            "qiniu_failed": qiniu_failed,
            "ids": payload.ids,
            "force": payload.force,
            "skipped_refs": skipped_refs,
        },
    )
    msg = f"批量删除完成，共 {deleted} 个"
    if skipped_refs:
        msg += f"，{len(skipped_refs)} 个因存在引用被跳过"
    if qiniu_failed > 0:
        msg += f"，其中 {qiniu_failed} 个七牛删除失败"
    return ResponseModel(
        code=200,
        msg=msg,
        data={"deleted": deleted, "qiniu_failed": qiniu_failed, "skipped_refs": skipped_refs},
    )


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

    prefix = (payload.prefix or "").strip()
    limit = max(1, min(int(payload.limit or 1000), 3000))
    try:
        sync_stats = sync_qiniu_resources(
            db,
            settings,
            prefix=prefix,
            limit=limit,
            user_id=current_user.id,
        )
    except RuntimeError as exc:
        db.rollback()
        return ResponseModel(code=500, msg=str(exc))

    db.commit()

    redis_client = RedisClient()
    redis_client.get_client().incr("resources:list:version")

    record_admin_action(
        user=current_user,
        action="resource.sync_qiniu",
        target_type="resource",
        target_id=prefix or "all",
        description=f"七牛云资源同步，扫描 {sync_stats.scanned}，新增 {sync_stats.created}，更新 {sync_stats.updated}",
        request=request,
        extra={
            "prefix": prefix,
            "limit": limit,
            "scanned": sync_stats.scanned,
            "created": sync_stats.created,
            "updated": sync_stats.updated,
        },
    )

    return ResponseModel(
        code=200,
        msg=f"同步完成：扫描 {sync_stats.scanned}，新增 {sync_stats.created}，更新 {sync_stats.updated}",
        data={
            "scanned": sync_stats.scanned,
            "created": sync_stats.created,
            "updated": sync_stats.updated,
        },
    )


@router.get("/{id}/references", response_model=ResponseModel[ResourceReferences])
def get_resource_references(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """查询资源引用关系（当前仅追踪文章内容/封面）"""
    resource = db.query(Resource).filter(Resource.id == id).first()
    if not resource:
        return ResponseModel(code=404, msg="资源不存在")

    refs = _find_referenced_articles(db, resource.key, resource.url)
    return ResponseModel(
        code=200,
        data=ResourceReferences(
            resource_id=resource.id,
            key=resource.key,
            article_refs=[ResourceArticleRef(id=item.id, title=item.title) for item in refs],
        ),
    )
