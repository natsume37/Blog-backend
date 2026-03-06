from datetime import datetime
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.deps import get_current_user, get_current_admin
from app.core.config import settings
from app.core.cache import redis_client
from app.models.article import Article, Tag
from app.models.site import SiteInfo
from app.models.user import User
from app.schemas.site import SiteStats, SiteConfig, MailConfig, MailTestPayload, CommentRiskConfig
from app.schemas.common import ResponseModel
from app.utils.audit import record_admin_action


router = APIRouter(prefix="/site", tags=["站点"])


# Site start date (you can change this)
SITE_START_DATE = datetime(2025, 11, 27)


def _get_site_val(db: Session, key: str, default: str) -> str:
    item = db.query(SiteInfo).filter(SiteInfo.key == key).first()
    return item.value if item else default


def _set_site_val(db: Session, key: str, value: str) -> None:
    item = db.query(SiteInfo).filter(SiteInfo.key == key).first()
    if not item:
        item = SiteInfo(key=key, value=value)
        db.add(item)
    else:
        item.value = value


def _get_json_list(db: Session, key: str) -> list[str]:
    raw = _get_site_val(db, key, "[]")
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
    except Exception:
        pass
    return []


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
        return _get_site_val(db, key, default)

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
        messageBoardTitle=get_val("message_board_title", "弹幕"),
        danmakuSpeed=int(get_val("danmaku_speed", "10")),
        danmakuOpacity=float(get_val("danmaku_opacity", "0.7")),
        danmakuFontSize=int(get_val("danmaku_font_size", "14")),
        danmakuInterval=int(get_val("danmaku_interval", "1200"))
    )
    
    # Cache the result (1 hour)
    redis_client.set(cache_key, config.model_dump(), expire=3600)
    
    return ResponseModel(code=200, data=config)


@router.put("/config", response_model=ResponseModel[SiteConfig])
def update_site_config(
    config: SiteConfig,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新站点配置 (仅管理员)"""
    if not current_user.is_admin:
        return ResponseModel(code=403, msg="权限不足")
        
    def set_val(key, value):
        _set_site_val(db, key, str(value))
    
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
    set_val("message_board_title", config.messageBoardTitle)
    set_val("danmaku_speed", str(config.danmakuSpeed))
    set_val("danmaku_opacity", str(config.danmakuOpacity))
    set_val("danmaku_font_size", str(config.danmakuFontSize))
    set_val("danmaku_interval", str(config.danmakuInterval))
    
    db.commit()
    
    # Invalidate cache
    redis_client.delete("site_config")

    record_admin_action(
        user=current_user,
        action="site.config.update",
        target_type="site_config",
        target_id="global",
        description="更新站点配置",
        request=request,
    )
    
    return ResponseModel(code=200, data=config, msg="配置已更新")


@router.get("/mail-config", response_model=ResponseModel[MailConfig])
def get_mail_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    data = MailConfig(
        smtpHost=_get_site_val(db, "mail_smtp_host", settings.SMTP_HOST),
        smtpPort=int(_get_site_val(db, "mail_smtp_port", str(settings.SMTP_PORT))),
        smtpUser=_get_site_val(db, "mail_smtp_user", settings.SMTP_USER),
        smtpPassword=_get_site_val(db, "mail_smtp_password", settings.SMTP_PASSWORD),
        emailsFromEmail=_get_site_val(db, "mail_from_email", settings.EMAILS_FROM_EMAIL),
        emailsFromName=_get_site_val(db, "mail_from_name", settings.EMAILS_FROM_NAME),
    )
    return ResponseModel(code=200, data=data)


@router.put("/mail-config", response_model=ResponseModel[MailConfig])
def update_mail_config(
    payload: MailConfig,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    _set_site_val(db, "mail_smtp_host", payload.smtpHost.strip())
    _set_site_val(db, "mail_smtp_port", str(payload.smtpPort))
    _set_site_val(db, "mail_smtp_user", payload.smtpUser.strip())
    _set_site_val(db, "mail_smtp_password", payload.smtpPassword)
    _set_site_val(db, "mail_from_email", payload.emailsFromEmail.strip())
    _set_site_val(db, "mail_from_name", payload.emailsFromName.strip())
    db.commit()
    record_admin_action(
        user=current_user,
        action="mail.config.update",
        target_type="mail_config",
        target_id="global",
        description="更新邮件配置",
        request=request,
    )
    return ResponseModel(code=200, msg="邮件配置已保存", data=payload)


@router.post("/mail-config/test", response_model=ResponseModel)
def test_mail_config(
    payload: MailTestPayload,
    request: Request,
    current_user: User = Depends(get_current_admin)
):
    try:
        msg = MIMEMultipart()
        from_name = payload.emailsFromName
        try:
            from_name.encode("ascii")
        except UnicodeEncodeError:
            from_name = Header(from_name, "utf-8").encode()

        msg["From"] = formataddr((from_name, payload.emailsFromEmail))
        msg["To"] = formataddr((None, payload.emailTo))
        msg["Subject"] = Header("博客后台邮件配置测试", "utf-8")
        msg.attach(MIMEText("这是一封测试邮件，说明当前 SMTP 配置可用。", "plain", "utf-8"))

        if payload.smtpPort == 465:
            server = smtplib.SMTP_SSL(payload.smtpHost, payload.smtpPort, timeout=10)
        else:
            server = smtplib.SMTP(payload.smtpHost, payload.smtpPort, timeout=10)
            server.starttls()
        server.login(payload.smtpUser, payload.smtpPassword)
        server.sendmail(payload.emailsFromEmail, [payload.emailTo], msg.as_string())
        server.quit()
        record_admin_action(
            user=current_user,
            action="mail.config.test",
            target_type="mail_config",
            target_id=payload.emailTo,
            description=f"测试邮件发送成功: {payload.emailTo}",
            request=request,
        )
        return ResponseModel(code=200, msg=f"测试邮件已发送到 {payload.emailTo}")
    except Exception as e:
        record_admin_action(
            user=current_user,
            action="mail.config.test",
            target_type="mail_config",
            target_id=payload.emailTo,
            description=f"测试邮件发送失败: {payload.emailTo}",
            request=request,
            extra={"error": str(e)},
        )
        return ResponseModel(code=500, msg=f"测试失败: {e}")


@router.get("/comment-risk-config", response_model=ResponseModel[CommentRiskConfig])
def get_comment_risk_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    data = CommentRiskConfig(
        sensitiveWords=_get_json_list(db, "comment_sensitive_words"),
        blockedIps=_get_json_list(db, "comment_blocked_ips"),
        autoRejectEnabled=_get_site_val(db, "comment_auto_reject_enabled", "false") == "true",
    )
    return ResponseModel(code=200, data=data)


@router.put("/comment-risk-config", response_model=ResponseModel[CommentRiskConfig])
def update_comment_risk_config(
    payload: CommentRiskConfig,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    _set_site_val(db, "comment_sensitive_words", json.dumps(payload.sensitiveWords, ensure_ascii=False))
    _set_site_val(db, "comment_blocked_ips", json.dumps(payload.blockedIps, ensure_ascii=False))
    _set_site_val(db, "comment_auto_reject_enabled", "true" if payload.autoRejectEnabled else "false")
    db.commit()
    record_admin_action(
        user=current_user,
        action="comment.risk.update",
        target_type="comment_risk_config",
        target_id="global",
        description="更新评论风控配置",
        request=request,
        extra={"words": len(payload.sensitiveWords), "blocked_ips": len(payload.blockedIps), "auto_reject": payload.autoRejectEnabled},
    )
    return ResponseModel(code=200, msg="评论风控配置已保存", data=payload)
