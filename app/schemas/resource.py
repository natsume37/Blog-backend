from typing import Optional
from pydantic import BaseModel, ConfigDict
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
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int]
    created_at: datetime

class ResourceList(BaseModel):
    total: int
    items: list[ResourceResponse]


class ResourceBatchDelete(BaseModel):
    ids: list[int]
    force: bool = False


class ResourceSyncRequest(BaseModel):
    prefix: str = ""
    limit: int = 1000


class ResourceArticleRef(BaseModel):
    id: int
    title: str


class ResourceReferences(BaseModel):
    resource_id: int
    key: str
    article_refs: list[ResourceArticleRef]
