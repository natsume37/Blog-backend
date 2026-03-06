import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_current_admin
from app.core.database import get_db
from app.models.site import SiteInfo
from app.models.user import User
from app.schemas.ai import AIDraftRequest, AIDraftResponse, AISummaryRequest, AISummaryResponse, AIConfig
from app.schemas.common import ResponseModel
from app.services.ai_article import generate_article_draft, generate_article_summary


router = APIRouter(prefix="/ai", tags=["AI"])
logger = logging.getLogger(__name__)


def _parse_bool(value: str, default: bool) -> bool:
    value = (value or "").strip().lower()
    if value in {"true", "1", "yes", "y", "on"}:
        return True
    if value in {"false", "0", "no", "n", "off"}:
        return False
    return default


def _get_ai_settings(db: Session, settings: Settings) -> Settings:
    key_defaults = {
        "ai_enabled": "true" if settings.AI_ENABLED else "false",
        "ai_provider": settings.AI_PROVIDER,
        "ai_base_url": settings.AI_BASE_URL or "",
        "ai_api_key": settings.AI_API_KEY or "",
        "ai_model": settings.AI_MODEL,
        "ai_timeout_seconds": str(settings.AI_TIMEOUT_SECONDS),
    }
    values: dict[str, str] = {}
    for key, default in key_defaults.items():
        item = db.query(SiteInfo).filter(SiteInfo.key == key).first()
        values[key] = item.value if item else default

    timeout = settings.AI_TIMEOUT_SECONDS
    try:
        timeout = max(1, int(float(values["ai_timeout_seconds"])))
    except (TypeError, ValueError):
        timeout = settings.AI_TIMEOUT_SECONDS

    return settings.model_copy(update={
        "AI_ENABLED": _parse_bool(values["ai_enabled"], settings.AI_ENABLED),
        "AI_PROVIDER": values["ai_provider"] or settings.AI_PROVIDER,
        "AI_BASE_URL": values["ai_base_url"] or None,
        "AI_API_KEY": values["ai_api_key"] or None,
        "AI_MODEL": values["ai_model"] or settings.AI_MODEL,
        "AI_TIMEOUT_SECONDS": timeout,
    })


def _save_ai_settings(db: Session, payload: AIConfig) -> None:
    config_map = {
        "ai_enabled": "true" if payload.ai_enabled else "false",
        "ai_provider": payload.ai_provider.strip(),
        "ai_base_url": payload.ai_base_url.strip(),
        "ai_api_key": payload.ai_api_key.strip(),
        "ai_model": payload.ai_model.strip(),
        "ai_timeout_seconds": str(payload.ai_timeout_seconds),
    }
    for key, value in config_map.items():
        item = db.query(SiteInfo).filter(SiteInfo.key == key).first()
        if not item:
            item = SiteInfo(key=key, value=value)
            db.add(item)
        else:
            item.value = value


@router.get("/config", response_model=ResponseModel[AIConfig])
def get_ai_config(
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    runtime = _get_ai_settings(db, settings)
    data = AIConfig(
        ai_enabled=runtime.AI_ENABLED,
        ai_provider=runtime.AI_PROVIDER,
        ai_base_url=runtime.AI_BASE_URL or "",
        ai_api_key=runtime.AI_API_KEY or "",
        ai_model=runtime.AI_MODEL,
        ai_timeout_seconds=runtime.AI_TIMEOUT_SECONDS,
    )
    return ResponseModel(code=200, data=data)


@router.put("/config", response_model=ResponseModel[AIConfig])
def update_ai_config(
    payload: AIConfig,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _save_ai_settings(db, payload)
    db.commit()
    runtime = _get_ai_settings(db, settings)
    data = AIConfig(
        ai_enabled=runtime.AI_ENABLED,
        ai_provider=runtime.AI_PROVIDER,
        ai_base_url=runtime.AI_BASE_URL or "",
        ai_api_key=runtime.AI_API_KEY or "",
        ai_model=runtime.AI_MODEL,
        ai_timeout_seconds=runtime.AI_TIMEOUT_SECONDS,
    )
    return ResponseModel(code=200, msg="AI 配置已更新", data=data)


@router.post("/article-draft", response_model=ResponseModel[AIDraftResponse])
def create_article_draft(
    payload: AIDraftRequest,
    _: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    """生成文章草稿（管理员）"""
    try:
        runtime = _get_ai_settings(db, settings)
        data = generate_article_draft(payload, runtime)
        if not data.get("content_markdown"):
            return ResponseModel(code=502, msg="AI 返回内容为空")
        return ResponseModel(code=200, msg="生成成功", data=AIDraftResponse(**data))
    except Exception as exc:
        logger.error("Generate AI draft failed: %s", exc, exc_info=True)
        return ResponseModel(code=500, msg="AI 草稿生成失败，请稍后重试")


@router.post("/article-summary", response_model=ResponseModel[AISummaryResponse])
def create_article_summary(
    payload: AISummaryRequest,
    _: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    """生成文章摘要（管理员）"""
    try:
        runtime = _get_ai_settings(db, settings)
        data = generate_article_summary(payload, runtime)
        if not data.get("summary"):
            return ResponseModel(code=502, msg="AI 返回摘要为空")
        return ResponseModel(code=200, msg="生成成功", data=AISummaryResponse(**data))
    except Exception as exc:
        logger.error("Generate AI summary failed: %s", exc, exc_info=True)
        return ResponseModel(code=500, msg="AI 摘要生成失败，请稍后重试")
