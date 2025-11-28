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
    
    class Config:
        from_attributes = True

