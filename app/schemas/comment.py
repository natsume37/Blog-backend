"""
评论相关 Schema
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class CommentCreate(BaseModel):
    """创建评论请求"""
    content_type: str = Field(default="article", description="内容类型: article, changelog, message_board")
    content_id: int = Field(..., description="内容ID")
    content: str = Field(..., min_length=1, max_length=2000, description="评论内容")
    parent_id: Optional[int] = Field(None, description="父评论ID（回复评论时使用）")
    reply_to_id: Optional[int] = Field(None, description="回复目标用户ID")


class CommentUpdate(BaseModel):
    """更新评论请求"""
    content: Optional[str] = Field(None, min_length=1, max_length=2000)
    is_approved: Optional[bool] = None


class CommentUser(BaseModel):
    """评论用户信息"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    nickname: str
    avatar: Optional[str] = None

class CommentReply(BaseModel):
    """子评论（回复）响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    user: CommentUser
    reply_to: Optional[CommentUser] = None
    like_count: int = 0
    created_at: datetime
    is_liked: bool = False

class CommentResponse(BaseModel):
    """评论响应（包含回复列表）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    content_type: str = "article"
    content_id: int
    user: CommentUser
    like_count: int = 0
    created_at: datetime
    is_liked: bool = False
    replies: List[CommentReply] = Field(default_factory=list)
    reply_count: int = 0

class CommentAdminItem(BaseModel):
    """管理员评论列表项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    article_id: int
    article_title: str
    user: CommentUser
    is_approved: bool
    created_at: datetime
