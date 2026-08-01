from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class MessageBase(BaseModel):
    content: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    email: Optional[str] = None


class MessageCreate(MessageBase):
    parent_id: Optional[int] = None


class MessageResponse(MessageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None
    parent_id: Optional[int] = None

class CommentBase(BaseModel):
    content: str
    nickname: Optional[str] = "游客"
    avatar: Optional[str] = ""
    email: Optional[str] = ""


class CommentCreate(CommentBase):
    article_id: int
    parent_id: Optional[int] = None


class CommentResponse(CommentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    article_id: int
    created_at: Optional[datetime] = None
    parent_id: Optional[int] = None
