import base64
import mimetypes
import time
import uuid
from typing import Any
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from qiniu import Auth, put_data
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.resource import Resource
from app.services.plugins.base import (
    PluginActionSpec,
    PluginAdminPage,
    PluginSettingField,
    PluginSettingOption,
    PluginSpec,
)
from app.services.plugins.builtin.ai_plugin import resolve_ai_runtime_settings
from app.services.plugins.storage import get_plugin_settings_map, save_plugin_settings_map
from app.utils.qiniu import generate_qiniu_timestamp_url


AI_IMAGE_PLUGIN_ID = "ai-image-studio"
_ALLOWED_SIZES = {"1024x1024", "1536x1024", "1024x1536"}
_ALLOWED_QUALITIES = {"low", "medium", "high", "auto"}
_ALLOWED_FORMATS = {"png", "jpeg", "webp"}
_ALLOWED_BACKGROUNDS = {"auto", "opaque", "transparent"}


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if raw in {"true", "1", "yes", "y", "on"}:
        return True
    if raw in {"false", "0", "no", "n", "off"}:
        return False
    return default


def _parse_int(value: Any, default: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _normalize_choice(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def load_ai_image_plugin_settings(db: Session, settings: Settings) -> dict[str, Any]:
    ai_runtime = resolve_ai_runtime_settings(db, settings, plugin_enabled=True)
    defaults = {
        "provider": ai_runtime.AI_PROVIDER,
        "base_url": ai_runtime.AI_BASE_URL or "",
        "api_key": ai_runtime.AI_API_KEY or "",
        "image_model": "gpt-image-1",
        "default_size": "1024x1024",
        "default_quality": "high",
        "default_output_format": "png",
        "default_background": "auto",
        "timeout_seconds": str(max(10, ai_runtime.AI_TIMEOUT_SECONDS)),
        "save_to_library_default": "true",
    }
    values = {**defaults, **get_plugin_settings_map(db, AI_IMAGE_PLUGIN_ID)}
    return {
        "provider": str(values.get("provider") or defaults["provider"]).strip() or defaults["provider"],
        "base_url": str(values.get("base_url") or defaults["base_url"]).strip(),
        "api_key": str(values.get("api_key") or defaults["api_key"]).strip(),
        "image_model": str(values.get("image_model") or defaults["image_model"]).strip() or defaults["image_model"],
        "default_size": _normalize_choice(values.get("default_size"), _ALLOWED_SIZES, defaults["default_size"]),
        "default_quality": _normalize_choice(values.get("default_quality"), _ALLOWED_QUALITIES, defaults["default_quality"]),
        "default_output_format": _normalize_choice(values.get("default_output_format"), _ALLOWED_FORMATS, defaults["default_output_format"]),
        "default_background": _normalize_choice(values.get("default_background"), _ALLOWED_BACKGROUNDS, defaults["default_background"]),
        "timeout_seconds": _parse_int(values.get("timeout_seconds"), max(10, ai_runtime.AI_TIMEOUT_SECONDS), min_value=10, max_value=180),
        "save_to_library_default": _parse_bool(values.get("save_to_library_default"), True),
    }


def save_ai_image_plugin_settings(db: Session, payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    current = load_ai_image_plugin_settings(db, settings)
    values = {
        "provider": str(payload.get("provider", current["provider"])).strip() or current["provider"],
        "base_url": str(payload.get("base_url", current["base_url"])).strip(),
        "api_key": str(payload.get("api_key", current["api_key"])).strip(),
        "image_model": str(payload.get("image_model", current["image_model"])).strip() or current["image_model"],
        "default_size": _normalize_choice(payload.get("default_size", current["default_size"]), _ALLOWED_SIZES, current["default_size"]),
        "default_quality": _normalize_choice(payload.get("default_quality", current["default_quality"]), _ALLOWED_QUALITIES, current["default_quality"]),
        "default_output_format": _normalize_choice(
            payload.get("default_output_format", current["default_output_format"]),
            _ALLOWED_FORMATS,
            current["default_output_format"],
        ),
        "default_background": _normalize_choice(
            payload.get("default_background", current["default_background"]),
            _ALLOWED_BACKGROUNDS,
            current["default_background"],
        ),
        "timeout_seconds": str(
            _parse_int(payload.get("timeout_seconds", current["timeout_seconds"]), current["timeout_seconds"], min_value=10, max_value=180),
        ),
        "save_to_library_default": "true"
        if _parse_bool(payload.get("save_to_library_default", current["save_to_library_default"]), current["save_to_library_default"])
        else "false",
    }
    save_plugin_settings_map(db, AI_IMAGE_PLUGIN_ID, values)
    return load_ai_image_plugin_settings(db, settings)


def _resolve_ai_image_runtime(db: Session, settings: Settings) -> dict[str, Any]:
    values = load_ai_image_plugin_settings(db, settings)
    return {
        "provider": values["provider"],
        "base_url": values["base_url"],
        "api_key": values["api_key"],
        "image_model": values["image_model"],
        "default_size": values["default_size"],
        "default_quality": values["default_quality"],
        "default_output_format": values["default_output_format"],
        "default_background": values["default_background"],
        "timeout_seconds": values["timeout_seconds"],
        "save_to_library_default": values["save_to_library_default"],
    }


def _request_json(url: str, *, method: str = "GET", timeout: int = 30, api_key: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json", "User-Agent": "BlogPluginMarket/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if payload is not None:
        import json

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(url, data=body, method=method, headers=headers)
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        import json

        raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw or "{}")
    if not isinstance(data, dict):
        raise RuntimeError("AI 生图接口返回格式异常")
    return data


def _download_binary(url: str, timeout: int = 60) -> tuple[bytes, str]:
    req = urllib_request.Request(url, headers={"User-Agent": "BlogPluginMarket/1.0"})
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get_content_type() or "application/octet-stream"
        return resp.read(), content_type


def _mime_for_format(output_format: str) -> str:
    if output_format == "jpeg":
        return "image/jpeg"
    if output_format == "webp":
        return "image/webp"
    return "image/png"


def _data_url_from_bytes(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _build_prompt(prompt: str, negative_prompt: str) -> str:
    clean_prompt = prompt.strip()
    clean_negative = negative_prompt.strip()
    if not clean_negative:
        return clean_prompt
    return f"{clean_prompt}\n\nAvoid the following elements: {clean_negative}"


def _build_qiniu_preview_url(key: str, settings: Settings) -> str:
    base_url = f"{settings.QINIU_DOMAIN.rstrip('/')}/{key.lstrip('/')}"
    expire_seconds = settings.QINIU_TIMESTAMP_EXPIRE if settings.is_qiniu_timestamp_enabled else 3600
    if settings.is_qiniu_timestamp_enabled:
        return generate_qiniu_timestamp_url(
            base_url=base_url,
            key=key,
            timestamp_key=settings.QINIU_TIMESTAMP_KEY,
            expire_seconds=expire_seconds,
        )
    auth = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
    return auth.private_download_url(base_url, expires=expire_seconds)


def _upload_to_resource_library(
    db: Session,
    *,
    prompt: str,
    image_bytes: bytes,
    mime_type: str,
    settings: Settings,
) -> dict[str, Any]:
    if not settings.is_qiniu_enabled:
        raise RuntimeError("图库未配置七牛云，暂时无法自动入库")

    ext = mimetypes.guess_extension(mime_type) or ".png"
    key = f"img/ai/{time.strftime('%Y%m%d')}/{uuid.uuid4().hex}{ext}"
    token = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY).upload_token(settings.QINIU_BUCKET, key, 3600)
    result, info = put_data(token, key, image_bytes, mime_type=mime_type, check_crc=True)
    status_code = getattr(info, "status_code", 0) or 0
    if status_code < 200 or status_code >= 300:
        raise RuntimeError(f"七牛上传失败，状态码 {status_code}")
    if not isinstance(result, dict) or not result.get("key"):
        raise RuntimeError("七牛上传成功但未返回 key")

    base_url = f"{settings.QINIU_DOMAIN.rstrip('/')}/{key.lstrip('/')}"
    filename = (prompt.strip()[:24] or "ai-image").replace("/", "-")
    resource = Resource(
        filename=f"{filename}{ext}",
        key=key,
        url=base_url,
        media_type="image",
        mime_type=mime_type,
        size=len(image_bytes),
        user_id=None,
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return {
        "saved": True,
        "resource_id": resource.id,
        "resource_key": resource.key,
        "resource_url": resource.url,
        "preview_url": _build_qiniu_preview_url(resource.key, settings),
    }


def test_ai_image_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()
    base_url = str(runtime.get("base_url") or "").strip()
    api_key = str(runtime.get("api_key") or "").strip()
    image_model = str(runtime.get("image_model") or "").strip()
    provider = str(runtime.get("provider") or "").strip()
    timeout = int(runtime.get("timeout_seconds") or 30)

    if not base_url:
        return {"ok": False, "message": "Base URL 为空", "provider": provider, "model": image_model, "latency_ms": 0}
    if not api_key:
        return {"ok": False, "message": "API Key 为空", "provider": provider, "model": image_model, "latency_ms": 0}

    payload = _request_json(
        f"{base_url.rstrip('/')}/models",
        timeout=timeout,
        api_key=api_key,
    )
    model_ids = {
        str(item.get("id") or "").strip()
        for item in (payload.get("data") or [])
        if isinstance(item, dict)
    }
    latency_ms = int((time.perf_counter() - start) * 1000)
    if model_ids and image_model not in model_ids:
        return {
            "ok": False,
            "message": f"接口连通，但模型 `{image_model}` 未出现在 /models 列表中",
            "provider": provider,
            "model": image_model,
            "latency_ms": latency_ms,
        }
    return {
        "ok": True,
        "message": "AI 生图服务连接成功",
        "provider": provider,
        "model": image_model,
        "latency_ms": latency_ms,
    }


def friendly_ai_image_error(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"AI 生图接口返回错误（HTTP {exc.code}），请检查 Base URL、模型和授权信息。"
    if isinstance(exc, URLError):
        return f"AI 生图接口网络异常：{getattr(exc, 'reason', exc)}"
    if isinstance(exc, TimeoutError):
        return "AI 生图请求超时，请稍后重试或调大超时。"
    text = str(exc).strip()
    return f"AI 生图失败：{text[:180]}" if text else "AI 生图失败，请稍后重试。"


def ai_image_plugin_default_enabled(_: Session, __: Settings) -> bool:
    return True


def _generate_images(payload: dict[str, Any], db: Session, settings: Settings) -> dict[str, Any]:
    runtime = _resolve_ai_image_runtime(db, settings)
    prompt = str(payload.get("prompt") or "").strip()
    if len(prompt) < 4:
        raise RuntimeError("提示词至少需要 4 个字符")

    negative_prompt = str(payload.get("negative_prompt") or "").strip()
    size = _normalize_choice(payload.get("size", runtime["default_size"]), _ALLOWED_SIZES, runtime["default_size"])
    quality = _normalize_choice(payload.get("quality", runtime["default_quality"]), _ALLOWED_QUALITIES, runtime["default_quality"])
    output_format = _normalize_choice(
        payload.get("output_format", runtime["default_output_format"]),
        _ALLOWED_FORMATS,
        runtime["default_output_format"],
    )
    background = _normalize_choice(
        payload.get("background", runtime["default_background"]),
        _ALLOWED_BACKGROUNDS,
        runtime["default_background"],
    )
    image_count = _parse_int(payload.get("n", 1), 1, min_value=1, max_value=4)
    save_to_library = _parse_bool(payload.get("save_to_library"), runtime["save_to_library_default"])

    request_payload: dict[str, Any] = {
        "model": runtime["image_model"],
        "prompt": _build_prompt(prompt, negative_prompt),
        "size": size,
        "quality": quality,
        "n": image_count,
        "output_format": output_format,
    }
    if background != "auto":
        request_payload["background"] = background

    response = _request_json(
        f"{str(runtime['base_url']).rstrip('/')}/images/generations",
        method="POST",
        timeout=int(runtime["timeout_seconds"]),
        api_key=str(runtime["api_key"]),
        payload=request_payload,
    )
    raw_items = response.get("data")
    if not isinstance(raw_items, list) or not raw_items:
        raise RuntimeError("AI 生图接口未返回图片数据")

    items: list[dict[str, Any]] = []
    saved_count = 0
    library_available = bool(settings.is_qiniu_enabled)
    revised_prompt = str(response.get("revised_prompt") or "").strip()

    for index, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            continue
        item_prompt = str(raw_item.get("revised_prompt") or revised_prompt or prompt).strip()
        image_url = str(raw_item.get("url") or "").strip()
        b64_data = str(raw_item.get("b64_json") or "").strip()
        mime_type = _mime_for_format(output_format)
        image_bytes: bytes | None = None
        preview_url = image_url
        data_url = ""

        if b64_data:
            image_bytes = base64.b64decode(b64_data)
            data_url = _data_url_from_bytes(image_bytes, mime_type)
            preview_url = data_url
        elif image_url:
            if save_to_library and library_available:
                image_bytes, mime_type = _download_binary(image_url, timeout=int(runtime["timeout_seconds"]))
        else:
            raise RuntimeError("AI 生图接口返回的条目缺少 url 或 b64_json")

        saved_payload = {
            "saved": False,
            "resource_id": None,
            "resource_key": "",
            "resource_url": "",
            "preview_url": preview_url,
        }
        if save_to_library and library_available:
            if image_bytes is None and image_url:
                image_bytes, mime_type = _download_binary(image_url, timeout=int(runtime["timeout_seconds"]))
            if image_bytes is None:
                raise RuntimeError("图片下载失败，无法保存到图库")
            saved_payload = _upload_to_resource_library(
                db,
                prompt=item_prompt,
                image_bytes=image_bytes,
                mime_type=mime_type,
                settings=settings,
            )
            preview_url = saved_payload["preview_url"]
            saved_count += 1

        items.append({
            "index": index,
            "prompt": item_prompt,
            "url": preview_url or image_url or data_url,
            "source_url": image_url,
            "data_url": data_url,
            "mime_type": mime_type,
            "saved": saved_payload["saved"],
            "resource_id": saved_payload["resource_id"],
            "resource_key": saved_payload["resource_key"],
            "resource_url": saved_payload["resource_url"],
        })

    return {
        "ok": True,
        "message": (
            f"已生成 {len(items)} 张图片"
            + (f"，并已入库 {saved_count} 张" if saved_count else "")
            + ("。当前图库未配置七牛云，结果仅用于预览。" if save_to_library and not library_available else "")
        ),
        "provider": runtime["provider"],
        "model": runtime["image_model"],
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "revised_prompt": revised_prompt,
        "size": size,
        "quality": quality,
        "output_format": output_format,
        "background": background,
        "save_to_library": save_to_library,
        "library_available": library_available,
        "items": items,
    }


def ai_image_plugin_call_action(action: str, payload: dict[str, Any], db: Session, settings: Settings) -> dict[str, Any]:
    runtime = _resolve_ai_image_runtime(db, settings)
    if action == "test_connection":
        return test_ai_image_runtime(runtime)
    if action == "generate":
        return _generate_images(payload, db, settings)
    raise KeyError(action)


AI_IMAGE_PLUGIN = PluginSpec(
    plugin_id=AI_IMAGE_PLUGIN_ID,
    name="AI 生图工坊",
    version="1.0.0",
    description="使用 OpenAI 兼容接口生成图片，并可直接落到站点图库。",
    category="automation",
    source="official",
    settings_schema=[
        PluginSettingField(key="provider", label="提供方", type="text", description="例如 openai-compatible。", default="openai-compatible"),
        PluginSettingField(key="base_url", label="Base URL", type="text", required=True, placeholder="https://api.openai.com/v1"),
        PluginSettingField(key="api_key", label="API Key", type="password", required=True, secret=True, placeholder="sk-..."),
        PluginSettingField(key="image_model", label="生图模型", type="text", required=True, placeholder="gpt-image-1"),
        PluginSettingField(
            key="default_size",
            label="默认尺寸",
            type="select",
            default="1024x1024",
            options=[
                PluginSettingOption(label="方图 1024x1024", value="1024x1024"),
                PluginSettingOption(label="横图 1536x1024", value="1536x1024"),
                PluginSettingOption(label="竖图 1024x1536", value="1024x1536"),
            ],
        ),
        PluginSettingField(
            key="default_quality",
            label="默认质量",
            type="select",
            default="high",
            options=[
                PluginSettingOption(label="自动", value="auto"),
                PluginSettingOption(label="低", value="low"),
                PluginSettingOption(label="中", value="medium"),
                PluginSettingOption(label="高", value="high"),
            ],
        ),
        PluginSettingField(
            key="default_output_format",
            label="默认格式",
            type="select",
            default="png",
            options=[
                PluginSettingOption(label="PNG", value="png"),
                PluginSettingOption(label="JPEG", value="jpeg"),
                PluginSettingOption(label="WEBP", value="webp"),
            ],
        ),
        PluginSettingField(
            key="default_background",
            label="默认背景",
            type="select",
            default="auto",
            options=[
                PluginSettingOption(label="自动", value="auto"),
                PluginSettingOption(label="纯色背景", value="opaque"),
                PluginSettingOption(label="透明背景", value="transparent"),
            ],
        ),
        PluginSettingField(key="timeout_seconds", label="超时秒数", type="number", description="请求超时时间，最小 10 秒。", default=90),
        PluginSettingField(key="save_to_library_default", label="默认入库图库", type="switch", description="生成后默认上传到站点图库。", default=True),
    ],
    admin_pages=[
        PluginAdminPage(
            path="/admin/plugins/ai-image-studio/studio",
            route_name="PluginAIImageStudio",
            title="AI 生图工坊",
            menu_label="AI 生图",
            component_key="plugin.ai.image",
            icon="PictureFilled",
            layout="workspace",
        ),
    ],
    actions=[
        PluginActionSpec(name="test_connection", label="测试连接", description="校验生图接口连通性。"),
        PluginActionSpec(name="generate", label="生成图片", description="按提示词生成图片并返回预览结果。"),
    ],
    get_settings=load_ai_image_plugin_settings,
    save_settings=save_ai_image_plugin_settings,
    call_action=ai_image_plugin_call_action,
    icon="PictureFilled",
    author="Martin",
    publisher="natsume37",
    homepage="https://martin88.xyz",
    docs_url="https://github.com/natsume37/Blog-plugin-market/tree/main/plugins/ai-image-studio",
    repository_url="https://github.com/natsume37/Blog-backend",
    support_url="https://github.com/natsume37/Blog-backend/issues",
    issues_url="https://github.com/natsume37/Blog-backend/issues",
    license="MIT",
    verified=True,
    featured=True,
    install_strategy="builtin-toggle",
    runtime_type="builtin",
    min_app_version="1.0.0",
    features=["提示词生图", "尺寸与质量控制", "结果预览", "一键入库图库"],
    keywords=["ai", "image", "prompt", "gallery", "qiniu"],
    tags=["automation", "design", "media", "official"],
    capabilities=["image_generation", "image_preview", "resource_library"],
    permissions=["network", "site_settings", "resource_write"],
    auto_install=True,
    default_enabled=ai_image_plugin_default_enabled,
)
