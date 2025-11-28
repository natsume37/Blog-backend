from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.changelog import Changelog
from app.models.user import User
from app.schemas.changelog import Changelog as ChangelogSchema, ChangelogCreate, ChangelogUpdate
from app.schemas.common import ResponseModel


router = APIRouter(prefix="/changelogs", tags=["建站日志"])


@router.get("", response_model=ResponseModel[List[ChangelogSchema]])
def get_changelogs(db: Session = Depends(get_db)):
    """获取所有建站日志"""
    logs = db.query(Changelog).order_by(Changelog.created_at.desc()).all()
    return ResponseModel(code=200, data=logs)


@router.post("", response_model=ResponseModel[ChangelogSchema])
def create_changelog(
    log: ChangelogCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建建站日志 (管理员)"""
    if not current_user.is_admin:
        return ResponseModel(code=403, msg="权限不足")
        
    db_log = Changelog(**log.model_dump())
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    return ResponseModel(code=200, data=db_log, msg="创建成功")


@router.put("/{id}", response_model=ResponseModel[ChangelogSchema])
def update_changelog(
    id: int,
    log: ChangelogUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新建站日志 (管理员)"""
    if not current_user.is_admin:
        return ResponseModel(code=403, msg="权限不足")
        
    db_log = db.query(Changelog).filter(Changelog.id == id).first()
    if not db_log:
        return ResponseModel(code=404, msg="日志不存在")
        
    db_log.version = log.version
    db_log.content = log.content
    db.commit()
    db.refresh(db_log)
    return ResponseModel(code=200, data=db_log, msg="更新成功")


@router.delete("/{id}", response_model=ResponseModel)
def delete_changelog(
    id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除建站日志 (管理员)"""
    if not current_user.is_admin:
        return ResponseModel(code=403, msg="权限不足")
        
    db_log = db.query(Changelog).filter(Changelog.id == id).first()
    if not db_log:
        return ResponseModel(code=404, msg="日志不存在")
        
    db.delete(db_log)
    db.commit()
    return ResponseModel(code=200, msg="删除成功")
