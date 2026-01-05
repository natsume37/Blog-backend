from datetime import datetime
import json
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.cache import redis_client
from app.models.article import Article, Tag
from app.models.site import SiteInfo
from app.models.user import User
from app.schemas.site import SiteStats, SiteConfig
from app.schemas.common import ResponseModel


router = APIRouter(prefix="/site", tags=["站点"])


# Site start date (you can change this)
SITE_START_DATE = datetime(2025, 11, 27)


@router.get("/info", response_model=ResponseModel[SiteStats])
def get_site_info(db: Session = Depends(get_db)):
    """获取站点统计信息"""
    # Count articles
    article_count = db.query(func.count(Article.id)).filter(Article.is_published == True).scalar() or 0
    
    # Count tags
    tag_count = db.query(func.count(Tag.id)).scalar() or 0
    
    # Sum view count
    view_count = db.query(func.sum(Article.view_count)).scalar() or 0
    
    # Calculate running days
    run_days = (datetime.now() - SITE_START_DATE).days
    
    return ResponseModel(
        code=200,
        data=SiteStats(
            articleCount=article_count,
            tagCount=tag_count,
            viewCount=view_count,
            runDays=run_days
        )
    )


@router.get("/config", response_model=ResponseModel[SiteConfig])
def get_site_config(db: Session = Depends(get_db)):
    """获取站点配置"""
    # Try cache first
    cache_key = "site_config"
    cached_config = redis_client.get(cache_key)
    if cached_config:
        return ResponseModel(code=200, data=SiteConfig(**cached_config))

    # Helper to get value or default
    def get_val(key, default):
        item = db.query(SiteInfo).filter(SiteInfo.key == key).first()
        return item.value if item else default

    # Defaults
    default_sentences = json.dumps(["相信美好，遇见美好。", "生活明朗，万物可爱。", "保持热爱，奔赴山海。"], ensure_ascii=False)
    
    # 默认留言板背景图
    default_banners = json.dumps([
        "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?q=80&w=2070&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?q=80&w=2070&auto=format&fit=crop",
        "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?q=80&w=2070&auto=format&fit=crop"
    ], ensure_ascii=False)
    
    config = SiteConfig(
        siteName=get_val("site_name", "Miyazaki Blog"),
        siteDescription=get_val("site_description", "相信美好，遇见美好。"),
        siteAvatar=get_val("site_avatar", "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?q=80&w=1780&auto=format&fit=crop"),
        siteAuthor=get_val("site_author", "POETIZE"),
        heroTitle=get_val("hero_title", "看见"),
        heroBgImage=get_val("hero_bg_image", "https://images.unsplash.com/photo-1490730141103-6cac27aaab94?q=80&w=2070&auto=format&fit=crop"),
        heroSentences=json.loads(get_val("hero_sentences", default_sentences)),
        showNotice=get_val("show_notice", "true") == "true",
        noticeText=get_val("notice_text", "欢迎访问我的个人博客！这里记录了我的学习笔记和生活感悟。本站持续更新中..."),
        aboutContent=get_val("about_content", "# 关于我\n\n这里是我的个人介绍..."),
        messageBoardBanners=json.loads(get_val("message_board_banners", default_banners)),
        danmakuSpeed=int(get_val("danmaku_speed", "10")),
        danmakuOpacity=float(get_val("danmaku_opacity", "0.7")),
        danmakuFontSize=int(get_val("danmaku_font_size", "14"))
    )
    
    # Cache the result (1 hour)
    redis_client.set(cache_key, config.model_dump(), expire=3600)
    
    return ResponseModel(code=200, data=config)


@router.put("/config", response_model=ResponseModel[SiteConfig])
def update_site_config(
    config: SiteConfig,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新站点配置 (仅管理员)"""
    if not current_user.is_admin:
        return ResponseModel(code=403, msg="权限不足")
        
    def set_val(key, value):
        item = db.query(SiteInfo).filter(SiteInfo.key == key).first()
        if not item:
            item = SiteInfo(key=key, value=str(value))
            db.add(item)
        else:
            item.value = str(value)
    
    set_val("site_name", config.siteName)
    set_val("site_description", config.siteDescription)
    set_val("site_avatar", config.siteAvatar)
    set_val("site_author", config.siteAuthor)
    set_val("hero_title", config.heroTitle)
    set_val("hero_bg_image", config.heroBgImage)
    set_val("hero_sentences", json.dumps(config.heroSentences, ensure_ascii=False))
    set_val("show_notice", "true" if config.showNotice else "false")
    set_val("notice_text", config.noticeText)
    set_val("about_content", config.aboutContent)
    set_val("message_board_banners", json.dumps(config.messageBoardBanners, ensure_ascii=False))
    set_val("danmaku_speed", str(config.danmakuSpeed))
    set_val("danmaku_opacity", str(config.danmakuOpacity))
    set_val("danmaku_font_size", str(config.danmakuFontSize))
    
    db.commit()
    
    # Invalidate cache
    redis_client.delete("site_config")
    
    return ResponseModel(code=200, data=config, msg="配置已更新")
