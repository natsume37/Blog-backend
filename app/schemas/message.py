from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class MessageBase(BaseModel):
    content: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    email: Optional[str] = None


class MessageCreate(MessageBase):
    parent_id: Optional[int] = None


class MessageResponse(MessageBase):
    id: int
    created_at: Optional[datetime] = None
    parent_id: Optional[int] = None

    class Config:
        from_attributes = True


class CommentBase(BaseModel):
    content: str
    nickname: Optional[str] = "游客"
    avatar: Optional[str] = ""
    email: Optional[str] = ""


class CommentCreate(CommentBase):
    article_id: int
    parent_id: Optional[int] = None


class CommentResponse(CommentBase):
    id: int
    article_id: int
    created_at: Optional[datetime] = None
    parent_id: Optional[int] = None

    class Config:
        from_attributes = True
