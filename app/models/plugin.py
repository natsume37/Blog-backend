from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class PluginInstall(Base):
    __tablename__ = "plugin_installs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plugin_id = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    description = Column(String(500), default="")
    category = Column(String(50), default="general")
    source = Column(String(50), default="official")
    is_installed = Column(Boolean, default=True)
    is_enabled = Column(Boolean, default=False)
    installed_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PluginSetting(Base):
    __tablename__ = "plugin_settings"

    __table_args__ = (
        UniqueConstraint("plugin_id", "key", name="uq_plugin_settings_plugin_key"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plugin_id = Column(String(100), nullable=False, index=True)
    key = Column(String(100), nullable=False)
    value = Column(Text, default="")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
