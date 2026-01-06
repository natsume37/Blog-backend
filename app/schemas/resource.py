from typing import Optional
from pydantic import BaseModel
from datetime import datetime

class ResourceBase(BaseModel):
    filename: str
    key: str
    url: str
    media_type: str
    mime_type: Optional[str] = None
    size: Optional[int] = 0

class ResourceCreate(ResourceBase):
    pass

class ResourceResponse(ResourceBase):
    id: int
    user_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True

class ResourceList(BaseModel):
    total: int
    items: list[ResourceResponse]
