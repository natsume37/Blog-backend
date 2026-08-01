from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = ""
    banner_url: Optional[str] = None
    quote: Optional[str] = None
    quote_author: Optional[str] = None


class CategoryCreate(CategoryBase):
    sort_order: Optional[int] = 0


class CategoryResponse(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sort_order: int
    article_count: int = 0  # 文章数量
    created_at: Optional[datetime] = None
    
    # Include new fields in response
    banner_url: Optional[str] = None
    quote: Optional[str] = None
    quote_author: Optional[str] = None

class TagBase(BaseModel):
    name: str
    color: Optional[str] = "#3b82f6"


class TagCreate(TagBase):
    pass


class TagResponse(TagBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None

class ArticleBase(BaseModel):
    title: str
    slug: Optional[str] = None
    summary: Optional[str] = ""
    content: str
    cover: Optional[str] = ""
    seo_title: Optional[str] = ""
    seo_description: Optional[str] = ""
    seo_keywords: Optional[str] = ""
    category_id: Optional[int] = None
    is_published: Optional[bool] = True
    is_top: Optional[bool] = False
    is_recommend: Optional[bool] = False
    is_hidden: Optional[bool] = False
    visibility: Optional[str] = "public"
    
    # 权限控制
    is_protected: bool = False
    protection_question: Optional[str] = None
    protection_answer: Optional[str] = None


class ArticleCreate(ArticleBase):
    tag_ids: Optional[List[int]] = Field(default_factory=list)


class ArticleUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    cover: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_keywords: Optional[str] = None
    category_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None
    is_published: Optional[bool] = None
    is_top: Optional[bool] = None
    is_recommend: Optional[bool] = None
    is_hidden: Optional[bool] = None
    visibility: Optional[str] = None
    
    # 权限控制
    is_protected: Optional[bool] = None
    protection_question: Optional[str] = None
    protection_answer: Optional[str] = None


class ArticleBatchAction(BaseModel):
    ids: List[int]
    action: str  # publish | unpublish | recycle | restore | delete


class ArticleWechatRenderRequest(BaseModel):
    title: Optional[str] = ""
    summary: Optional[str] = ""
    content: str
    include_summary: bool = True


class ArticleWechatRenderResponse(BaseModel):
    html: str
    plain_text: str = ""
    warnings: List[str] = Field(default_factory=list)


class ArticleListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    summary: Optional[str] = ""
    cover: Optional[str] = ""
    createTime: str
    categoryName: Optional[str] = ""
    viewCount: int
    commentCount: int
    likeCount: int

class ArticleAdminListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    visibility: str = "public"

class ArticleDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    slug: Optional[str] = None
    summary: Optional[str] = ""
    content: str
    cover: Optional[str] = ""
    seo_title: Optional[str] = ""
    seo_description: Optional[str] = ""
    seo_keywords: Optional[str] = ""
    createTime: str
    createdAt: Optional[datetime] = None
    categoryName: Optional[str] = ""
    category: Optional[CategoryResponse] = None
    tags: List[TagResponse] = Field(default_factory=list)
    viewCount: int
    commentCount: int
    likeCount: int
    is_top: bool = False
    is_recommend: bool = False
    is_hidden: bool = False
    is_published: bool = True
    category_id: Optional[int] = None
    visibility: str = "public"
    is_protected: Optional[bool] = False
    protection_question: Optional[str] = None

class CategoryWithArticles(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    articles: List[ArticleListItem]
