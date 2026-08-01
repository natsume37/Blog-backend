from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ToolItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., min_length=3, max_length=500)
    logo: Optional[str] = Field(default="", max_length=500)
    description: Optional[str] = Field(default="", max_length=255)
    category: Optional[str] = Field(default="推荐工具", max_length=50)
    tool_type: Optional[str] = Field(default="website", max_length=30)
    badge: Optional[str] = Field(default="", max_length=40)
    tags: Optional[str] = Field(default="", max_length=255)
    site_color: Optional[str] = Field(default="", max_length=20)
    subscription_url: Optional[str] = Field(default="", max_length=500)
    open_mode: Optional[str] = Field(default="new_tab", max_length=20)


class ToolItemCreate(ToolItemBase):
    sort_order: int = 0
    is_featured: bool = False
    status: str = Field(default="published", max_length=20)


class ToolItemUpdate(ToolItemCreate):
    pass


class ToolItemPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    logo: str = ""
    description: str = ""
    category: str = "推荐工具"
    tool_type: str = "website"
    badge: str = ""
    tags: str = ""
    site_color: str = ""
    subscription_url: str = ""
    open_mode: str = "new_tab"
    is_featured: bool = False
    created_at: datetime

class ToolItemAdmin(ToolItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sort_order: int = 0
    is_featured: bool = False
    status: str = "draft"
    created_at: datetime
    updated_at: Optional[datetime] = None
