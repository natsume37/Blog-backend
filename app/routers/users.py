from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_admin
from app.core.security import get_password_hash
from app.models.user import User
from app.schemas.user import UserInfo, UserAdminUpdate, UserAdminCreate
from app.schemas.common import ResponseModel, PagedData


router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("/admin/list", response_model=ResponseModel[PagedData[UserInfo]])
def get_users(
    current: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """获取用户列表 (管理员)"""
    query = db.query(User)
    
    if keyword:
        query = query.filter(
            (User.username.contains(keyword)) | 
            (User.nickname.contains(keyword)) |
            (User.email.contains(keyword))
        )
    
    query = query.order_by(User.created_at.desc())
    
    total = query.count()
    users = query.offset((current - 1) * size).limit(size).all()
    
    records = [UserInfo(
        id=u.id,
        username=u.username,
        nickname=u.nickname or u.username,
        avatar=u.avatar or "",
        email=u.email or "",
        intro=u.intro or "",
        is_admin=u.is_admin,
        is_active=u.is_active,
        created_at=u.created_at
    ) for u in users]
    
    return ResponseModel(
        code=200,
        data=PagedData(
            records=records,
            total=total,
            current=current,
            size=size
        )
    )


@router.post("/admin", response_model=ResponseModel)
def create_user(
    user_data: UserAdminCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """创建用户 (管理员)"""
    # 检查用户名是否存在
    if db.query(User).filter(User.username == user_data.username).first():
        return ResponseModel(code=400, msg="用户名已存在")
    
    # 检查邮箱是否存在
    if user_data.email and db.query(User).filter(User.email == user_data.email).first():
        return ResponseModel(code=400, msg="邮箱已被注册")
    
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        nickname=user_data.nickname or user_data.username,
        is_admin=user_data.is_admin,
        is_active=True
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return ResponseModel(code=200, msg="创建成功", data={"id": user.id})


@router.put("/admin/{user_id}", response_model=ResponseModel)
def update_user(
    user_id: int,
    user_data: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """更新用户 (管理员)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ResponseModel(code=404, msg="用户不存在")
    
    # 防止修改超级管理员
    if user.id == 1 and current_user.id != 1:
        return ResponseModel(code=403, msg="无权修改超级管理员")
    
    if user_data.nickname is not None:
        user.nickname = user_data.nickname
    if user_data.email is not None:
        # 检查邮箱是否被其他用户使用
        existing = db.query(User).filter(
            User.email == user_data.email,
            User.id != user_id
        ).first()
        if existing:
            return ResponseModel(code=400, msg="邮箱已被其他用户使用")
        user.email = user_data.email
    if user_data.is_admin is not None:
        # 不能取消自己的管理员权限
        if user_id == current_user.id and not user_data.is_admin:
            return ResponseModel(code=400, msg="不能取消自己的管理员权限")
        user.is_admin = user_data.is_admin
    if user_data.is_active is not None:
        # 不能禁用自己
        if user_id == current_user.id and not user_data.is_active:
            return ResponseModel(code=400, msg="不能禁用自己")
        user.is_active = user_data.is_active
    if user_data.password:
        user.hashed_password = get_password_hash(user_data.password)
    
    db.commit()
    return ResponseModel(code=200, msg="更新成功")


@router.delete("/admin/{user_id}", response_model=ResponseModel)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除用户 (管理员)"""
    if user_id == current_user.id:
        return ResponseModel(code=400, msg="不能删除自己")
    
    if user_id == 1:
        return ResponseModel(code=400, msg="不能删除超级管理员")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return ResponseModel(code=404, msg="用户不存在")
    
    db.delete(user)
    db.commit()
    
    return ResponseModel(code=200, msg="删除成功")
