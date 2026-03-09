from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FriendLinkBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., min_length=3, max_length=500)
    logo: Optional[str] = Field(default="", max_length=500)
    description: Optional[str] = Field(default="", max_length=255)
    group_name: Optional[str] = Field(default="推荐站点", max_length=50)
    contact: Optional[str] = Field(default="", max_length=120)
    reciprocal_url: Optional[str] = Field(default="", max_length=500)
    site_color: Optional[str] = Field(default="", max_length=20)


class FriendLinkApply(FriendLinkBase):
    pass


class FriendLinkCreate(FriendLinkBase):
    sort_order: int = 0
    is_featured: bool = False
    status: str = Field(default="approved", max_length=20)
    review_note: Optional[str] = Field(default="", max_length=255)


class FriendLinkUpdate(FriendLinkCreate):
    pass


class FriendLinkPublic(BaseModel):
    id: int
    name: str
    url: str
    logo: str = ""
    description: str = ""
    group_name: str = "推荐站点"
    site_color: str = ""
    is_featured: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class FriendLinkAdmin(FriendLinkBase):
    id: int
    sort_order: int = 0
    is_featured: bool = False
    status: str = "pending"
    review_note: str = ""
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
