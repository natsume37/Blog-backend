from sqlalchemy import Column, Integer, String, DateTime, Float
from sqlalchemy.sql import func
from app.core.database import Base


class VisitLog(Base):
    __tablename__ = "visit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ip = Column(String(50), nullable=False, index=True)
    location = Column(String(100), default="未知")
    province = Column(String(50), default="")
    city = Column(String(50), default="")
    path = Column(String(255), default="")
    method = Column(String(10), default="GET")
    user_agent = Column(String(500), default="")
    status_code = Column(Integer, default=200)
    process_time = Column(Float, default=0.0)
    
    created_at = Column(DateTime, server_default=func.now())
