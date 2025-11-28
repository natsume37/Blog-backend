from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, ForeignKey, Table, and_
from sqlalchemy.orm import relationship, foreign
from sqlalchemy.sql import func
from app.core.database import Base


# Many-to-many relationship table for articles and tags
article_tags = Table(
    "article_tags",
    Base.metadata,
    Column("article_id", Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
)


# 文章点赞记录表
class ArticleLike(Base):
    __tablename__ = "article_likes"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    ip_address = Column(String(50), nullable=True)  # 未登录用户使用 IP 限制
    created_at = Column(DateTime, server_default=func.now())


# 评论点赞记录表
class CommentLike(Base):
    __tablename__ = "comment_likes"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    comment_id = Column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255), default="")
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    articles = relationship("Article", back_populates="category")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    color = Column(String(20), default="#3b82f6")
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    articles = relationship("Article", secondary=article_tags, back_populates="tags")


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    summary = Column(String(500), default="")
    content = Column(Text, nullable=False)
    cover = Column(String(500), default="")
    
    # Foreign keys
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    
    # Stats
    view_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    
    # Status
    is_published = Column(Boolean, default=True)
    is_top = Column(Boolean, default=False)
    is_recommend = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    category = relationship("Category", back_populates="articles")
    tags = relationship("Tag", secondary=article_tags, back_populates="articles")
    
    # 使用 primaryjoin 定义多态关联
    comments = relationship(
        "Comment",
        primaryjoin="and_(foreign(Comment.content_id) == Article.id, Comment.content_type == 'article')",
        cascade="all, delete-orphan",
        viewonly=True,  # 避免 SQLAlchemy 尝试写入 content_type
    )
