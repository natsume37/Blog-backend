from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class FriendLink(Base):
    __tablename__ = "friend_links"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="站点名称")
    url = Column(String(500), nullable=False, unique=True, comment="站点链接")
    logo = Column(String(500), nullable=True, default="", comment="站点图标/Logo")
    description = Column(String(255), nullable=True, default="", comment="站点简介")
    group_name = Column(String(50), nullable=True, default="推荐站点", comment="分组名称")
    contact = Column(String(120), nullable=True, default="", comment="联系方式")
    reciprocal_url = Column(String(500), nullable=True, default="", comment="互链页面地址")
    site_color = Column(String(20), nullable=True, default="", comment="站点主题色")
    sort_order = Column(Integer, nullable=False, default=0, comment="排序，越小越靠前")
    is_featured = Column(Boolean, nullable=False, default=False, comment="是否精选")
    status = Column(String(20), nullable=False, default="pending", comment="状态: pending/approved/rejected/offline")
    review_note = Column(String(255), nullable=True, default="", comment="审核备注")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
