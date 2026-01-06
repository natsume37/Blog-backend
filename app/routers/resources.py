from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user_optional, get_current_admin
from app.models.resource import Resource
from app.models.user import User
from app.schemas.resource import ResourceCreate, ResourceResponse, ResourceList
from app.schemas.common import ResponseModel, PagedData
from app.core.cache import RedisClient
from app.core.config import get_settings, Settings
from qiniu import Auth, BucketManager

router = APIRouter(prefix="/resources", tags=["资源管理"])

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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(lambda: Settings())
):
    """获取资源列表 (仅管理员)"""
    # 获取当前列表缓存版本号
    redis_client = RedisClient()
    version = redis_client.get_client().get("resources:list:version") or "1"
    
    # 缓存 Key (包含版本号)
    cache_key = f"resources:list:v{version}:{current}:{size}:{type or 'all'}"
    
    cached_data = redis_client.get(cache_key)
    if cached_data:
        return ResponseModel(code=200, data=PagedData(**cached_data))

    query = db.query(Resource)
    
    if type:
        query = query.filter(Resource.media_type == type)
        
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
    db.delete(resource)
    db.commit()
    
    # 3. 清除相关缓存（版本号法）
    redis_client = RedisClient()
    redis_client.get_client().incr("resources:list:version")
    
    return ResponseModel(code=200, msg="删除成功")
