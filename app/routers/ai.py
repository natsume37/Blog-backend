import logging
import json
import time
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_current_admin
from app.core.database import get_db
from app.models.site import SiteInfo
from app.models.user import User
from app.schemas.ai import (
    AIDraftRequest,
    AIDraftResponse,
    AISummaryRequest,
    AISummaryResponse,
    AIConfig,
    AIConfigTestResult,
)
from app.schemas.common import ResponseModel
from app.services.ai_article import generate_article_draft, generate_article_summary
from app.utils.audit import record_admin_action


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


def _friendly_ai_error(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"AI 接口返回错误（HTTP {exc.code}），请检查 Base URL、模型与 API Key。"
    if isinstance(exc, URLError):
        reason = str(getattr(exc, "reason", exc))
        return f"AI 接口网络异常：{reason}"
    if isinstance(exc, TimeoutError):
        return "AI 请求超时，请提高 AI 超时时间或稍后重试。"
    text = str(exc).strip()
    if text:
        return f"AI 生成失败：{text[:180]}"
    return "AI 生成失败，请稍后重试。"


def _test_ai_endpoint(runtime: Settings) -> AIConfigTestResult:
    start = time.perf_counter()
    if not runtime.AI_ENABLED:
        return AIConfigTestResult(
            ok=False,
            message="AI 当前未启用（ai_enabled=false）",
            provider=runtime.AI_PROVIDER,
            model=runtime.AI_MODEL,
            latency_ms=0,
        )
    if not runtime.AI_BASE_URL:
        return AIConfigTestResult(
            ok=False,
            message="AI_BASE_URL 为空",
            provider=runtime.AI_PROVIDER,
            model=runtime.AI_MODEL,
            latency_ms=0,
        )
    if not runtime.AI_API_KEY:
        return AIConfigTestResult(
            ok=False,
            message="AI_API_KEY 为空",
            provider=runtime.AI_PROVIDER,
            model=runtime.AI_MODEL,
            latency_ms=0,
        )

    payload = {
        "model": runtime.AI_MODEL,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
        "temperature": 0,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    endpoint = f"{runtime.AI_BASE_URL.rstrip('/')}/chat/completions"
    req = urllib_request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {runtime.AI_API_KEY}",
        },
    )

    with urllib_request.urlopen(req, timeout=runtime.AI_TIMEOUT_SECONDS) as resp:
        if resp.status < 200 or resp.status >= 300:
            raise RuntimeError(f"AI 接口状态码异常: {resp.status}")
        _ = resp.read()

    latency_ms = int((time.perf_counter() - start) * 1000)
    return AIConfigTestResult(
        ok=True,
        message="AI 连通性测试通过",
        provider=runtime.AI_PROVIDER,
        model=runtime.AI_MODEL,
        latency_ms=latency_ms,
    )


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
    request: Request,
    current_user: User = Depends(get_current_admin),
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
    record_admin_action(
        user=current_user,
        action="ai.config.update",
        target_type="ai_config",
        target_id="global",
        description="更新 AI 配置",
        request=request,
        extra={"provider": data.ai_provider, "model": data.ai_model, "enabled": data.ai_enabled},
    )
    return ResponseModel(code=200, msg="AI 配置已更新", data=data)


@router.post("/test", response_model=ResponseModel[AIConfigTestResult])
def test_ai_config(
    request: Request,
    payload: AIConfig | None = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        runtime = _get_ai_settings(db, settings)
        if payload is not None:
            runtime = runtime.model_copy(update={
                "AI_ENABLED": payload.ai_enabled,
                "AI_PROVIDER": payload.ai_provider.strip() or runtime.AI_PROVIDER,
                "AI_BASE_URL": payload.ai_base_url.strip() or None,
                "AI_API_KEY": payload.ai_api_key.strip() or None,
                "AI_MODEL": payload.ai_model.strip() or runtime.AI_MODEL,
                "AI_TIMEOUT_SECONDS": max(1, int(payload.ai_timeout_seconds)),
            })
        result = _test_ai_endpoint(runtime)
        record_admin_action(
            user=current_user,
            action="ai.config.test",
            target_type="ai_config",
            target_id="global",
            description=f"AI 连通性测试{'成功' if result.ok else '失败'}",
            request=request,
            extra={"provider": result.provider, "model": result.model, "latency_ms": result.latency_ms, "ok": result.ok},
        )
        return ResponseModel(code=200 if result.ok else 400, msg=result.message, data=result)
    except Exception as exc:
        msg = _friendly_ai_error(exc)
        logger.error("Test AI config failed: %s", exc, exc_info=True)
        record_admin_action(
            user=current_user,
            action="ai.config.test",
            target_type="ai_config",
            target_id="global",
            description="AI 连通性测试失败",
            request=request,
            extra={"error": str(exc)},
        )
        return ResponseModel(
            code=500,
            msg=msg,
            data=AIConfigTestResult(
                ok=False,
                message=msg,
                provider=(payload.ai_provider if payload else settings.AI_PROVIDER),
                model=(payload.ai_model if payload else settings.AI_MODEL),
                latency_ms=0,
            ),
        )


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
        return ResponseModel(code=500, msg=_friendly_ai_error(exc))


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
        return ResponseModel(code=500, msg=_friendly_ai_error(exc))
