from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ChangelogBase(BaseModel):
    version: Optional[str] = None
    content: str


class ChangelogCreate(ChangelogBase):
    pass


class ChangelogUpdate(ChangelogBase):
    pass


class Changelog(ChangelogBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
