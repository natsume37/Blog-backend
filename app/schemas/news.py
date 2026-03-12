from pydantic import BaseModel


class NewsNowItem(BaseModel):
    id: str
    title: str
    url: str
    publishedAt: int | None = None


class NewsNowSourceGroup(BaseModel):
    sourceId: str
    sourceName: str
    sourceUrl: str
    description: str
    status: str = "live"
    items: list[NewsNowItem]
