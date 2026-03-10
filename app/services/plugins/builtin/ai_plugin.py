import json
import time
from typing import Any
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.site import SiteInfo
from app.services.plugins.base import (
    PluginActionSpec,
    PluginAdminPage,
    PluginSettingField,
    PluginSpec,
)


AI_PLUGIN_ID = "ai-assistant"


def _parse_bool(value: str, default: bool) -> bool:
    raw = (value or "").strip().lower()
    if raw in {"true", "1", "yes", "y", "on"}:
        return True
    if raw in {"false", "0", "no", "n", "off"}:
        return False
    return default


def _load_site_info_map(db: Session, defaults: dict[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, default in defaults.items():
        item = db.query(SiteInfo).filter(SiteInfo.key == key).first()
        values[key] = item.value if item else default
    return values


def load_ai_plugin_settings(db: Session, settings: Settings) -> dict[str, Any]:
    defaults = {
        "ai_enabled": "true" if settings.AI_ENABLED else "false",
        "ai_provider": settings.AI_PROVIDER,
        "ai_base_url": settings.AI_BASE_URL or "",
        "ai_api_key": settings.AI_API_KEY or "",
        "ai_model": settings.AI_MODEL,
        "ai_timeout_seconds": str(settings.AI_TIMEOUT_SECONDS),
    }
    values = _load_site_info_map(db, defaults)

    timeout = settings.AI_TIMEOUT_SECONDS
    try:
        timeout = max(1, int(float(values["ai_timeout_seconds"])))
    except (TypeError, ValueError):
        timeout = settings.AI_TIMEOUT_SECONDS

    return {
        "ai_enabled": _parse_bool(values["ai_enabled"], settings.AI_ENABLED),
        "ai_provider": values["ai_provider"] or settings.AI_PROVIDER,
        "ai_base_url": values["ai_base_url"] or "",
        "ai_api_key": values["ai_api_key"] or "",
        "ai_model": values["ai_model"] or settings.AI_MODEL,
        "ai_timeout_seconds": timeout,
    }


def save_ai_plugin_settings(db: Session, payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    current = load_ai_plugin_settings(db, settings)
    next_values = {
        "ai_enabled": "true" if bool(payload.get("ai_enabled", current["ai_enabled"])) else "false",
        "ai_provider": str(payload.get("ai_provider", current["ai_provider"])).strip(),
        "ai_base_url": str(payload.get("ai_base_url", current["ai_base_url"])).strip(),
        "ai_api_key": str(payload.get("ai_api_key", current["ai_api_key"])).strip(),
        "ai_model": str(payload.get("ai_model", current["ai_model"])).strip(),
        "ai_timeout_seconds": str(max(1, int(payload.get("ai_timeout_seconds", current["ai_timeout_seconds"])))),
    }
    for key, value in next_values.items():
        item = db.query(SiteInfo).filter(SiteInfo.key == key).first()
        if not item:
            item = SiteInfo(key=key, value=value)
            db.add(item)
        else:
            item.value = value
    return load_ai_plugin_settings(db, settings)


def resolve_ai_runtime_settings(db: Session, settings: Settings, *, plugin_enabled: bool = True) -> Settings:
    values = load_ai_plugin_settings(db, settings)
    return settings.model_copy(update={
        "AI_ENABLED": bool(plugin_enabled and values["ai_enabled"]),
        "AI_PROVIDER": values["ai_provider"] or settings.AI_PROVIDER,
        "AI_BASE_URL": values["ai_base_url"] or None,
        "AI_API_KEY": values["ai_api_key"] or None,
        "AI_MODEL": values["ai_model"] or settings.AI_MODEL,
        "AI_TIMEOUT_SECONDS": max(1, int(values["ai_timeout_seconds"])),
    })


def test_ai_runtime(runtime: Settings) -> dict[str, Any]:
    start = time.perf_counter()
    if not runtime.AI_ENABLED:
        return {
            "ok": False,
            "message": "AI 插件当前未启用",
            "provider": runtime.AI_PROVIDER,
            "model": runtime.AI_MODEL,
            "latency_ms": 0,
        }
    if not runtime.AI_BASE_URL:
        return {
            "ok": False,
            "message": "AI_BASE_URL 为空",
            "provider": runtime.AI_PROVIDER,
            "model": runtime.AI_MODEL,
            "latency_ms": 0,
        }
    if not runtime.AI_API_KEY:
        return {
            "ok": False,
            "message": "AI_API_KEY 为空",
            "provider": runtime.AI_PROVIDER,
            "model": runtime.AI_MODEL,
            "latency_ms": 0,
        }

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
    return {
        "ok": True,
        "message": "AI 连通性测试通过",
        "provider": runtime.AI_PROVIDER,
        "model": runtime.AI_MODEL,
        "latency_ms": latency_ms,
    }


def friendly_ai_error(exc: Exception) -> str:
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


def ai_plugin_default_enabled(_: Session, settings: Settings) -> bool:
    return bool(settings.AI_ENABLED)


def ai_plugin_call_action(action: str, payload: dict[str, Any], db: Session, settings: Settings) -> dict[str, Any]:
    runtime = resolve_ai_runtime_settings(db, settings, plugin_enabled=True)
    if action == "test_connection":
        return test_ai_runtime(runtime)
    raise KeyError(action)


AI_PLUGIN = PluginSpec(
    plugin_id=AI_PLUGIN_ID,
    name="AI 助手",
    version="1.0.0",
    description="封装文章草稿生成、摘要生成和 AI 工具配置。",
    category="automation",
    source="official",
    settings_schema=[
        PluginSettingField(key="ai_enabled", label="启用 AI", type="switch", description="控制 AI 草稿和摘要能力。", default=True),
        PluginSettingField(key="ai_provider", label="提供方", type="text", description="例如 openai-compatible。", default="openai-compatible"),
        PluginSettingField(key="ai_base_url", label="Base URL", type="text", required=True, placeholder="https://api.openai.com/v1"),
        PluginSettingField(key="ai_api_key", label="API Key", type="password", required=True, secret=True, placeholder="sk-..."),
        PluginSettingField(key="ai_model", label="模型", type="text", required=True, placeholder="gpt-4o-mini"),
        PluginSettingField(
            key="ai_timeout_seconds",
            label="超时秒数",
            type="number",
            description="请求超时时间，最小为 1 秒。",
            default=30,
        ),
    ],
    admin_pages=[
        PluginAdminPage(
            path="/admin/plugins/ai-assistant/settings",
            route_name="PluginAIAssistant",
            title="AI 助手配置",
            menu_label="AI 助手",
            component_key="plugin.ai.settings",
            icon="MagicStick",
        ),
    ],
    actions=[
        PluginActionSpec(name="test_connection", label="测试连接", description="校验 AI 服务连通性。"),
    ],
    get_settings=load_ai_plugin_settings,
    save_settings=save_ai_plugin_settings,
    call_action=ai_plugin_call_action,
    icon="MagicStick",
    author="Martin",
    publisher="natsume37",
    homepage="https://martin88.xyz",
    docs_url="https://github.com/natsume37/Blog-plugin-market/tree/main/plugins/ai-assistant",
    repository_url="https://github.com/natsume37/Blog-backend",
    support_url="https://github.com/natsume37/Blog-backend/issues",
    issues_url="https://github.com/natsume37/Blog-backend/issues",
    license="MIT",
    verified=True,
    featured=True,
    install_strategy="builtin-toggle",
    runtime_type="builtin",
    min_app_version="1.0.0",
    features=["AI 草稿", "AI 摘要", "MCP 工具", "模型配置"],
    keywords=["ai", "draft", "summary", "mcp", "editor"],
    tags=["automation", "editor", "official"],
    capabilities=["article_draft", "article_summary", "mcp_tools", "model_settings"],
    permissions=["network", "site_settings"],
    auto_install=True,
    default_enabled=ai_plugin_default_enabled,
)
