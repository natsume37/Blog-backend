from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    content = Column(Text, nullable=False)
    nickname = Column(String(50), default="游客")
    email = Column(String(100), default="")
    avatar = Column(String(500), default="")
    ip_address = Column(String(50), default="")
    
    # Reply to another message
    parent_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
