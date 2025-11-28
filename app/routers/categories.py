from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from app.core.database import get_db
from app.core.deps import get_current_admin
from app.models.article import Category, Tag, Article
from app.models.user import User
from app.schemas.article import (
    CategoryResponse, TagResponse, 
    CategoryCreate, TagCreate
)
from app.schemas.common import ResponseModel


router = APIRouter(tags=["分类与标签"])


# --- Categories ---

@router.post("/categories", response_model=ResponseModel)
def create_category(
    category_in: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """创建分类 (管理员)"""
    if db.query(Category).filter(Category.name == category_in.name).first():
        return ResponseModel(code=400, msg="分类已存在")
        
    category = Category(
        name=category_in.name,
        description=category_in.description,
        sort_order=category_in.sort_order
    )
    db.add(category)
    db.commit()
    return ResponseModel(code=200, msg="创建成功")


@router.put("/categories/{id}", response_model=ResponseModel)
def update_category(
    id: int,
    category_in: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """更新分类 (管理员)"""
    category = db.query(Category).filter(Category.id == id).first()
    if not category:
        return ResponseModel(code=404, msg="分类不存在")
        
    category.name = category_in.name
    category.description = category_in.description
    category.sort_order = category_in.sort_order
    db.commit()
    return ResponseModel(code=200, msg="更新成功")


@router.delete("/categories/{id}", response_model=ResponseModel)
def delete_category(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除分类 (管理员)"""
    category = db.query(Category).filter(Category.id == id).first()
    if not category:
        return ResponseModel(code=404, msg="分类不存在")
        
    db.delete(category)
    db.commit()
    return ResponseModel(code=200, msg="删除成功")


@router.get("/categories", response_model=ResponseModel[List[CategoryResponse]])
def get_categories(db: Session = Depends(get_db)):
    """获取所有分类（包含文章数量）"""
    # 查询分类及其已发布文章数量
    categories = db.query(Category).order_by(Category.sort_order).all()
    
    # 获取每个分类的已发布文章数量
    article_counts = dict(
        db.query(Article.category_id, func.count(Article.id))
        .filter(Article.is_published == True)
        .group_by(Article.category_id)
        .all()
    )
    
    data = [CategoryResponse(
        id=c.id,
        name=c.name,
        description=c.description,
        sort_order=c.sort_order,
        article_count=article_counts.get(c.id, 0),
        created_at=c.created_at
    ) for c in categories]
    return ResponseModel(code=200, data=data)


# --- Tags ---

@router.post("/tags", response_model=ResponseModel)
def create_tag(
    tag_in: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """创建标签 (管理员)"""
    if db.query(Tag).filter(Tag.name == tag_in.name).first():
        return ResponseModel(code=400, msg="标签已存在")
        
    tag = Tag(name=tag_in.name, color=tag_in.color)
    db.add(tag)
    db.commit()
    return ResponseModel(code=200, msg="创建成功")


@router.put("/tags/{id}", response_model=ResponseModel)
def update_tag(
    id: int,
    tag_in: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """更新标签 (管理员)"""
    tag = db.query(Tag).filter(Tag.id == id).first()
    if not tag:
        return ResponseModel(code=404, msg="标签不存在")
        
    tag.name = tag_in.name
    tag.color = tag_in.color
    db.commit()
    return ResponseModel(code=200, msg="更新成功")


@router.delete("/tags/{id}", response_model=ResponseModel)
def delete_tag(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除标签 (管理员)"""
    tag = db.query(Tag).filter(Tag.id == id).first()
    if not tag:
        return ResponseModel(code=404, msg="标签不存在")
        
    db.delete(tag)
    db.commit()
    return ResponseModel(code=200, msg="删除成功")


@router.get("/tags", response_model=ResponseModel[List[TagResponse]])
def get_tags(db: Session = Depends(get_db)):
    """获取所有标签"""
    tags = db.query(Tag).all()
    data = [TagResponse(
        id=t.id,
        name=t.name,
        color=t.color,
        created_at=t.created_at
    ) for t in tags]
    return ResponseModel(code=200, data=data)
