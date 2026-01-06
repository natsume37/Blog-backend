from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from app.core.database import Base

class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False, comment="原始文件名")
    key = Column(String(255), unique=True, nullable=False, comment="存储对象Key")
    url = Column(String(500), nullable=False, comment="访问链接")
    media_type = Column(String(50), nullable=False, comment="媒体类型: image/video/audio/other")
    mime_type = Column(String(100), nullable=True, comment="MIME类型")
    size = Column(Integer, default=0, comment="文件大小(字节)")
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
