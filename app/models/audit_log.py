from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(64), nullable=False, default="", index=True)
    action = Column(String(64), nullable=False, default="", index=True)
    target_type = Column(String(64), nullable=False, default="", index=True)
    target_id = Column(String(64), nullable=True, default="")
    description = Column(String(255), nullable=True, default="")
    request_path = Column(String(255), nullable=True, default="")
    request_method = Column(String(10), nullable=True, default="")
    ip = Column(String(50), nullable=True, default="")
    user_agent = Column(String(500), nullable=True, default="")
    extra = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
