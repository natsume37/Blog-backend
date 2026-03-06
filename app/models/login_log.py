from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func

from app.core.database import Base


class LoginLog(Base):
    __tablename__ = "login_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(64), nullable=False, default="", index=True)
    ip = Column(String(50), nullable=True, default="")
    user_agent = Column(String(500), nullable=True, default="")
    success = Column(Boolean, nullable=False, default=False, index=True)
    reason = Column(String(255), nullable=True, default="")
    created_at = Column(DateTime, server_default=func.now(), index=True)
