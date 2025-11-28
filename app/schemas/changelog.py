from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ChangelogBase(BaseModel):
    version: Optional[str] = None
    content: str


class ChangelogCreate(ChangelogBase):
    pass


class ChangelogUpdate(ChangelogBase):
    pass


class Changelog(ChangelogBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
