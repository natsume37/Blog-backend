from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = ""


class CategoryCreate(CategoryBase):
    sort_order: Optional[int] = 0


class CategoryResponse(CategoryBase):
    id: int
    sort_order: int
    article_count: int = 0  # 文章数量
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TagBase(BaseModel):
    name: str
    color: Optional[str] = "#3b82f6"


class TagCreate(TagBase):
    pass


class TagResponse(TagBase):
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ArticleBase(BaseModel):
    title: str
    summary: Optional[str] = ""
    content: str
    cover: Optional[str] = ""
    category_id: Optional[int] = None
    is_published: Optional[bool] = True
    is_top: Optional[bool] = False
    is_recommend: Optional[bool] = False


class ArticleCreate(ArticleBase):
    tag_ids: Optional[List[int]] = []


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    cover: Optional[str] = None
    category_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None
    is_published: Optional[bool] = None
    is_top: Optional[bool] = None
    is_recommend: Optional[bool] = None


class ArticleListItem(BaseModel):
    id: int
    title: str
    summary: Optional[str] = ""
    cover: Optional[str] = ""
    createTime: str
    categoryName: Optional[str] = ""
    viewCount: int
    commentCount: int
    likeCount: int

    class Config:
        from_attributes = True


class ArticleAdminListItem(ArticleListItem):
    is_published: bool
    is_top: bool
    is_recommend: bool


class ArticleDetail(BaseModel):
    id: int
    title: str
    summary: str
    content: str
    cover: str
    category_id: Optional[int] = None
    categoryName: Optional[str] = ""
    tags: List[TagResponse] = []
    viewCount: int
    commentCount: int
    likeCount: int
    is_published: bool
    is_top: bool
    is_recommend: bool
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True
