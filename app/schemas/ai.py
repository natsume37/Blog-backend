from typing import List, Optional
from pydantic import BaseModel, Field


class AIDraftRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=120, description="文章主题")
    style: str = Field(default="技术博客", max_length=40, description="写作风格")
    tone: str = Field(default="专业且易懂", max_length=40, description="语气")
    language: str = Field(default="zh-CN", max_length=12, description="语言")
    target_words: int = Field(default=1200, ge=200, le=5000, description="目标字数")
    keywords: List[str] = Field(default_factory=list, description="关键词")
    outline: List[str] = Field(default_factory=list, description="指定大纲")
    include_summary: bool = Field(default=True, description="是否需要摘要")
    existing_context: Optional[str] = Field(default="", max_length=8000, description="已有上下文")


class AIDraftResponse(BaseModel):
    title: str
    summary: str
    content_markdown: str
    tags_suggestion: List[str] = Field(default_factory=list)
    provider: str
    model: str
