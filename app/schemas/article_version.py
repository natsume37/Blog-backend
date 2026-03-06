from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ArticleVersionItem(BaseModel):
    id: int
    article_id: int
    title: str
    created_by: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}
