from pydantic import BaseModel
from typing import List, Optional


class SiteStats(BaseModel):
    articleCount: int
    tagCount: int
    viewCount: int
    runDays: int


class SiteConfig(BaseModel):
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
    messageBoardBanners: List[str] = []
    
    # Danmaku Settings
    danmakuSpeed: int = 10  # 弹幕速度 (秒)
    danmakuOpacity: float = 0.7  # 弹幕透明度
    danmakuFontSize: int = 14  # 弹幕字体大小
    
    class Config:
        from_attributes = True

