from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.core.database import Base


class ToolItem(Base):
    __tablename__ = "tool_items"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="工具名称")
    url = Column(String(500), nullable=False, unique=True, comment="工具链接")
    logo = Column(String(500), nullable=True, default="", comment="工具图标/Logo")
    description = Column(String(255), nullable=True, default="", comment="工具简介")
    category = Column(String(50), nullable=True, default="推荐工具", index=True, comment="工具分类")
    tool_type = Column(String(30), nullable=True, default="website", index=True, comment="工具类型")
    badge = Column(String(40), nullable=True, default="", comment="徽标文案")
    tags = Column(String(255), nullable=True, default="", comment="标签，逗号分隔")
    site_color = Column(String(20), nullable=True, default="", comment="主题色")
    subscription_url = Column(String(500), nullable=True, default="", comment="订阅地址")
    open_mode = Column(String(20), nullable=False, default="new_tab", comment="打开方式: new_tab/same_tab")
    sort_order = Column(Integer, nullable=False, default=0, index=True, comment="排序，越小越靠前")
    is_featured = Column(Boolean, nullable=False, default=False, comment="是否精选")
    status = Column(String(20), nullable=False, default="draft", index=True, comment="状态: draft/published/offline")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
