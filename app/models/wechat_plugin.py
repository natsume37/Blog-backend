from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.core.database import Base


class WechatBroadcastTask(Base):
    __tablename__ = "wechat_broadcast_tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_type = Column(String(32), nullable=False, index=True)
    source_type = Column(String(32), nullable=False, default="article")
    article_id = Column(Integer, nullable=True, index=True)
    title = Column(String(255), nullable=True, default="")
    draft_media_id = Column(String(255), nullable=True, index=True)
    broadcast_media_id = Column(String(255), nullable=True, index=True)
    publish_id = Column(String(255), nullable=True, index=True)
    msg_id = Column(String(255), nullable=True, index=True)
    preview_target = Column(String(255), nullable=True, default="")
    audience_type = Column(String(32), nullable=False, default="draft")
    audience_value = Column(String(255), nullable=True, default="")
    status = Column(String(64), nullable=False, default="pending", index=True)
    status_text = Column(String(255), nullable=True, default="")
    request_payload = Column(Text, nullable=True, default="")
    response_payload = Column(Text, nullable=True, default="")
    result_payload = Column(Text, nullable=True, default="")
    created_by = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    finished_at = Column(DateTime, nullable=True)


class WechatQrCodeRecord(Base):
    __tablename__ = "wechat_qrcode_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(120), nullable=True, default="")
    action_name = Column(String(32), nullable=False, index=True)
    scene_type = Column(String(16), nullable=False, default="str")
    scene_value = Column(String(255), nullable=False, index=True)
    ticket = Column(String(255), nullable=False, unique=True)
    url = Column(String(500), nullable=True, default="")
    image_url = Column(String(500), nullable=True, default="")
    expire_seconds = Column(Integer, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    request_payload = Column(Text, nullable=True, default="")
    response_payload = Column(Text, nullable=True, default="")
    created_by = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
