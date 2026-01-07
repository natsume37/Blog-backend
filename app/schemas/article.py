from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = ""
    banner_url: Optional[str] = None
    quote: Optional[str] = None
    quote_author: Optional[str] = None


class CategoryCreate(CategoryBase):
    sort_order: Optional[int] = 0


class CategoryResponse(CategoryBase):
    id: int
    sort_order: int
    article_count: int = 0  # 文章数量
    created_at: Optional[datetime] = None
    
    # Include new fields in response
    banner_url: Optional[str] = None
    quote: Optional[str] = None
    quote_author: Optional[str] = None

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
    is_hidden: Optional[bool] = False
    
    # 权限控制
    is_protected: bool = False
    protection_question: Optional[str] = None
    protection_answer: Optional[str] = None


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
    is_hidden: Optional[bool] = None
    
    # 权限控制
    is_protected: Optional[bool] = None
    protection_question: Optional[str] = None
    protection_answer: Optional[str] = None


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


class ArticleAdminListItem(BaseModel):
    id: int
    title: str
    summary: str
    cover: str
    createTime: str
    categoryName: str
    viewCount: int
    commentCount: int
    likeCount: int
    is_published: bool
    is_top: bool
    is_recommend: bool
    is_hidden: bool = False
    is_protected: bool = False

    class Config:
        from_attributes = True


class ArticleDetail(BaseModel):
    id: int
    title: str
    summary: Optional[str] = ""
    content: str
    cover: Optional[str] = ""
    createTime: str
    createdAt: Optional[datetime] = None
    categoryName: Optional[str] = ""
    category: Optional[CategoryResponse] = None
    tags: List[TagResponse] = []
    viewCount: int
    commentCount: int
    likeCount: int
    is_top: bool = False
    is_recommend: bool = False
    is_hidden: bool = False
    is_protected: Optional[bool] = False
    protection_question: Optional[str] = None

    class Config:
        from_attributes = True


class CategoryWithArticles(BaseModel):
    id: int
    name: str
    description: str
    articles: List[ArticleListItem]

    class Config:
        from_attributes = True
