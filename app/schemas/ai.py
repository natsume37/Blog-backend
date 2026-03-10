from typing import Any, Dict, List, Literal, Optional
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


class AISummaryRequest(BaseModel):
    title: str = Field(default="", max_length=200, description="文章标题")
    content_markdown: str = Field(..., min_length=20, max_length=100000, description="Markdown 正文")
    max_length: int = Field(default=140, ge=40, le=400, description="摘要最大长度（字符）")
    style: str = Field(default="简洁专业", max_length=40, description="摘要风格")


class AISummaryResponse(BaseModel):
    summary: str
    provider: str
    model: str


class AIConfig(BaseModel):
    ai_enabled: bool
    ai_provider: str
    ai_base_url: str
    ai_api_key: str
    ai_model: str
    ai_timeout_seconds: int


class AIConfigTestResult(BaseModel):
    ok: bool
    message: str
    provider: str
    model: str
    latency_ms: int


class MCPToolDefinition(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any] = Field(default_factory=dict)


class MCPToolCallRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=80, description="工具名称")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="工具参数")


class MCPToolContentItem(BaseModel):
    type: Literal["text"] = "text"
    text: str = ""


class MCPToolCallResponse(BaseModel):
    name: str
    mode: str = "fallback"
    provider: str
    model: str
    structuredContent: Dict[str, Any] = Field(default_factory=dict)
    content: List[MCPToolContentItem] = Field(default_factory=list)
    isError: bool = False
