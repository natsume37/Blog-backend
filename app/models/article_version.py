from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func

from app.core.database import Base


class ArticleVersion(Base):
    __tablename__ = "article_versions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    article_id = Column(Integer, nullable=False, index=True)
    title = Column(String(200), nullable=False, default="")
    slug = Column(String(255), nullable=True)
    summary = Column(String(500), nullable=True, default="")
    content = Column(Text, nullable=False, default="")
    cover = Column(String(500), nullable=True, default="")
    seo_title = Column(String(255), nullable=True, default="")
    seo_description = Column(String(500), nullable=True, default="")
    seo_keywords = Column(String(500), nullable=True, default="")
    category_id = Column(Integer, nullable=True)
    tag_ids = Column(Text, nullable=True, default="[]")
    is_published = Column(Integer, nullable=False, default=1)
    is_top = Column(Integer, nullable=False, default=0)
    is_recommend = Column(Integer, nullable=False, default=0)
    is_hidden = Column(Integer, nullable=False, default=0)
    visibility = Column(String(20), nullable=False, default="public")
    is_protected = Column(Integer, nullable=False, default=0)
    protection_question = Column(String(255), nullable=True, default="")
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
