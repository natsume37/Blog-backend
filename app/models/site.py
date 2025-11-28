from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.core.database import Base


class SiteInfo(Base):
    __tablename__ = "site_info"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(50), unique=True, nullable=False)
    value = Column(Text, default="")
    description = Column(String(255), default="")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
