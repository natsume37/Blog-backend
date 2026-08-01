from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional


class SiteStats(BaseModel):
    articleCount: int
    tagCount: int
    viewCount: int
    runDays: int


class SiteConfig(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # Site Info
    siteName: str
    siteDescription: str
    siteAvatar: str
    siteAuthor: str
    
    # Hero Section
    heroTitle: str
    heroBgImage: str
    heroSentences: List[str]
    
    # Modules
    showNotice: bool
    noticeText: str
    
    # About Me
    aboutContent: str = ""
    
    
    # Message Board Banners (留言页面背景图列表)
    messageBoardBanners: List[str] = Field(default_factory=list)
    messageBoardTitle: str = "弹幕"  # 留言板标题
    
    # Danmaku Settings
    danmakuSpeed: int = 10  # 弹幕速度 (秒)
    danmakuOpacity: float = 0.7  # 弹幕透明度
    danmakuFontSize: int = 14  # 弹幕字体大小
    danmakuInterval: int = 1200  # 弹幕生成间隔 (毫秒)
    
class MailConfig(BaseModel):
    smtpHost: str
    smtpPort: int
    smtpUser: str
    smtpPassword: str
    emailsFromEmail: str
    emailsFromName: str


class MailTestRequest(BaseModel):
    emailTo: str


class MailTestPayload(BaseModel):
    smtpHost: str
    smtpPort: int
    smtpUser: str
    smtpPassword: str
    emailsFromEmail: str
    emailsFromName: str
    emailTo: str


class CommentRiskConfig(BaseModel):
    sensitiveWords: List[str] = Field(default_factory=list)
    blockedIps: List[str] = Field(default_factory=list)
    autoRejectEnabled: bool = False
