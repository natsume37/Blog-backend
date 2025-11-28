"""评论数据模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class Comment(Base):
    """评论模型 - 支持嵌套评论和多种内容类型"""
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    content = Column(Text, nullable=False, comment="评论内容")
    
    # 内容类型: article, changelog, message_board
    content_type = Column(String(50), default="article", nullable=False, comment="内容类型")
    content_id = Column(Integer, default=0, nullable=False, comment="内容ID")
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="评论者ID")
    
    # 嵌套评论支持
    parent_id = Column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True, comment="父评论ID")
    reply_to_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="回复目标用户ID")
    
    # 状态
    is_approved = Column(Boolean, default=True, comment="是否审核通过")
    like_count = Column(Integer, default=0, comment="点赞数")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")

    # 关系
    user = relationship("User", foreign_keys=[user_id], backref="comments")
    reply_to = relationship("User", foreign_keys=[reply_to_id])
    
    # 子评论（自引用）
    children = relationship(
        "Comment",
        backref="parent",
        remote_side=[id],
        foreign_keys=[parent_id],
        cascade="all, delete-orphan",
        single_parent=True
    )
