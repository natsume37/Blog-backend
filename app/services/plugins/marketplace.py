import json
import logging
import time
from typing import Any
from urllib import parse as urlparse
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.plugin import PluginInstall
from app.services.plugins.registry import get_plugin_spec, list_plugins_with_state


logger = logging.getLogger(__name__)

_MARKET_CACHE: dict[str, Any] = {
    "expires_at": 0.0,
    "entries": [],
}


def _build_market_url(settings: Settings, path: str, *, base_url: str = "") -> str:
    target = str(path or "").strip()
    if not target:
        return ""
    if target.startswith(("https://", "http://", "file://")):
        return target
    if base_url:
        parent = base_url if base_url.endswith("/") else f"{base_url.rsplit('/', 1)[0]}/"
        return urlparse.urljoin(parent, target.lstrip("/"))
    normalized = target.lstrip("/")
    return f"{settings.plugin_market_raw_base_url}/{normalized}"


def _fetch_json(url: str, timeout: int) -> dict[str, Any]:
    req = urllib_request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "BlogPluginMarket/1.0",
        },
    )
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    payload = json.loads(raw or "{}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"插件市场响应格式异常: {url}")
    return payload


def _normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items


def _normalize_manifest(
    manifest: dict[str, Any],
    index_entry: dict[str, Any],
    settings: Settings,
    *,
    index_url: str,
    manifest_url: str,
) -> dict[str, Any] | None:
    plugin_id = str(manifest.get("plugin_id") or index_entry.get("plugin_id") or "").strip()
    if not plugin_id:
        return None

    publisher = manifest.get("publisher") if isinstance(manifest.get("publisher"), dict) else {}
    compatibility = manifest.get("compatibility") if isinstance(manifest.get("compatibility"), dict) else {}
    delivery = manifest.get("delivery") if isinstance(manifest.get("delivery"), dict) else {}

    screenshots_raw = manifest.get("screenshots") if isinstance(manifest.get("screenshots"), list) else []
    screenshots: list[dict[str, str]] = []
    for item in screenshots_raw:
        if isinstance(item, dict):
            url = _build_market_url(settings, str(item.get("url") or ""), base_url=manifest_url)
            if url:
                screenshots.append({
                    "label": str(item.get("label") or "").strip(),
                    "url": url,
                })

    return {
        "plugin_id": plugin_id,
        "name": str(manifest.get("name") or plugin_id).strip(),
        "version": str(manifest.get("version") or "0.0.0").strip(),
        "latest_version": str(manifest.get("version") or "0.0.0").strip(),
        "description": str(manifest.get("description") or "").strip(),
        "summary": str(manifest.get("summary") or manifest.get("description") or "").strip(),
        "category": str(manifest.get("category") or "general").strip(),
        "source": str(manifest.get("source") or "market").strip(),
        "icon": str(manifest.get("icon") or "Grid").strip() or "Grid",
        "author": str(manifest.get("author") or "").strip(),
        "homepage": _build_market_url(settings, str(manifest.get("homepage") or ""), base_url=manifest_url),
        "docs_url": _build_market_url(settings, str(manifest.get("docs_url") or ""), base_url=manifest_url),
        "repo_url": _build_market_url(settings, str(manifest.get("repo_url") or ""), base_url=manifest_url),
        "support_url": _build_market_url(settings, str(manifest.get("support_url") or ""), base_url=manifest_url),
        "issues_url": _build_market_url(settings, str(manifest.get("issues_url") or ""), base_url=manifest_url),
        "license": str(manifest.get("license") or "").strip(),
        "pricing": str(manifest.get("pricing") or "free").strip() or "free",
        "published_at": str(manifest.get("published_at") or "").strip(),
        "manifest_url": manifest_url,
        "readme_url": _build_market_url(
            settings,
            str(index_entry.get("readme_path") or manifest.get("readme_url") or ""),
            base_url=index_url,
        ),
        "changelog_url": _build_market_url(
            settings,
            str(index_entry.get("changelog_path") or manifest.get("changelog_url") or ""),
            base_url=index_url,
        ),
        "source_repo": _build_market_url(settings, str(manifest.get("source_repo") or ""), base_url=manifest_url),
        "keywords": _normalize_list(manifest.get("keywords")),
        "tags": _normalize_list(manifest.get("tags")),
        "features": _normalize_list(manifest.get("features")),
        "capabilities": _normalize_list(manifest.get("capabilities")),
        "permissions": _normalize_list(manifest.get("permissions")),
        "builtin": bool(manifest.get("builtin", False)),
        "marketplace": True,
        "official": bool(manifest.get("official", False)),
        "verified": bool(manifest.get("verified", False) or publisher.get("verified", False)),
        "featured": bool(manifest.get("featured", False)),
        "publisher": {
            "name": str(publisher.get("name") or manifest.get("publisher_name") or "").strip(),
            "url": _build_market_url(
                settings,
                str(publisher.get("url") or manifest.get("publisher_url") or ""),
                base_url=manifest_url,
            ),
            "verified": bool(publisher.get("verified", False) or manifest.get("verified", False)),
        },
        "compatibility": {
            "backend": str(compatibility.get("backend") or "").strip(),
            "frontend": str(compatibility.get("frontend") or "").strip(),
            "min_app_version": str(compatibility.get("min_app_version") or manifest.get("min_app_version") or "").strip(),
            "max_app_version": str(compatibility.get("max_app_version") or manifest.get("max_app_version") or "").strip(),
        },
        "delivery": {
            "type": str(delivery.get("type") or "catalog").strip() or "catalog",
            "entry_mode": str(delivery.get("entry_mode") or "local").strip() or "local",
            "install_strategy": str(delivery.get("install_strategy") or "catalog").strip() or "catalog",
            "runtime_type": str(delivery.get("runtime_type") or "catalog").strip() or "catalog",
            "entry_url": _build_market_url(settings, str(delivery.get("entry_url") or ""), base_url=manifest_url),
        },
        "screenshots": screenshots,
        "settings_schema": manifest.get("settings_schema") if isinstance(manifest.get("settings_schema"), list) else [],
        "admin_pages": manifest.get("admin_pages") if isinstance(manifest.get("admin_pages"), list) else [],
        "actions": manifest.get("actions") if isinstance(manifest.get("actions"), list) else [],
    }


def load_market_catalog(settings: Settings) -> list[dict[str, Any]]:
    if not settings.PLUGIN_MARKET_ENABLED:
        return []

    now = time.time()
    if _MARKET_CACHE["entries"] and now < float(_MARKET_CACHE["expires_at"]):
        return list(_MARKET_CACHE["entries"])

    index_url = settings.plugin_market_index_url
    try:
        index_payload = _fetch_json(index_url, settings.PLUGIN_MARKET_TIMEOUT_SECONDS)
        raw_entries = index_payload.get("plugins")
        if not isinstance(raw_entries, list):
            raise RuntimeError("插件市场索引缺少 plugins 数组")

        entries: list[dict[str, Any]] = []
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                continue
            manifest_path = str(raw_entry.get("manifest_path") or "").strip()
            manifest_payload = raw_entry
            manifest_url = _build_market_url(settings, manifest_path, base_url=index_url)
            if manifest_path:
                manifest_payload = _fetch_json(
                    manifest_url,
                    settings.PLUGIN_MARKET_TIMEOUT_SECONDS,
                )
            item = _normalize_manifest(
                manifest_payload,
                raw_entry,
                settings,
                index_url=index_url,
                manifest_url=manifest_url,
            )
            if item:
                entries.append(item)

        _MARKET_CACHE["entries"] = entries
        _MARKET_CACHE["expires_at"] = now + max(30, int(settings.PLUGIN_MARKET_CACHE_TTL_SECONDS))
        return list(entries)
    except (HTTPError, URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        if _MARKET_CACHE["entries"]:
            logger.warning("Load plugin marketplace failed, using stale cache: %s", exc)
            return list(_MARKET_CACHE["entries"])
        logger.warning("Load plugin marketplace failed, using builtin fallback: %s", exc)
        return []


def _merge_market_with_local(
    market_item: dict[str, Any],
    local_item: dict[str, Any] | None,
    record: PluginInstall | None,
) -> dict[str, Any]:
    spec = get_plugin_spec(str(market_item.get("plugin_id") or local_item.get("plugin_id") or ""))
    delivery = market_item.get("delivery") if isinstance(market_item.get("delivery"), dict) else {}
    compatibility = market_item.get("compatibility") if isinstance(market_item.get("compatibility"), dict) else {}
    publisher = market_item.get("publisher") if isinstance(market_item.get("publisher"), dict) else {}

    install_strategy = str(delivery.get("install_strategy") or local_item.get("delivery", {}).get("install_strategy", "catalog")) if local_item else str(delivery.get("install_strategy") or "catalog")
    runtime_type = str(delivery.get("runtime_type") or local_item.get("delivery", {}).get("runtime_type", "catalog")) if local_item else str(delivery.get("runtime_type") or "catalog")
    installable = bool(spec and install_strategy in {"builtin-toggle", "builtin"})
    activatable = bool(spec)
    installed = bool(record.is_installed) if record else bool(local_item.get("installed")) if local_item else False
    enabled = bool(record.is_enabled) if record else bool(local_item.get("enabled")) if local_item else False
    latest_version = str(market_item.get("latest_version") or market_item.get("version") or "").strip()
    installed_version = (
        str(record.version).strip()
        if record and record.is_installed
        else str((local_item or {}).get("installed_version") or "").strip()
    )
    upgrade_available = bool(installed and installed_version and latest_version and installed_version != latest_version)

    return {
        **(local_item or {}),
        **market_item,
        "installed": installed,
        "enabled": enabled,
        "installable": installable,
        "activatable": activatable,
        "upgrade_available": upgrade_available,
        "builtin": bool(market_item.get("builtin", False) or (local_item or {}).get("builtin", False)),
        "marketplace": True,
        "verified": bool(market_item.get("verified", False) or (local_item or {}).get("verified", False)),
        "featured": bool(market_item.get("featured", False) or (local_item or {}).get("featured", False)),
        "installed_version": installed_version,
        "status": (
            "enabled"
            if enabled
            else "update-available"
            if upgrade_available
            else "installed"
            if installed
            else "available"
            if installable
            else "catalog"
        ),
        "settings_schema": (local_item or {}).get("settings_schema", market_item.get("settings_schema", [])),
        "admin_pages": (local_item or {}).get("admin_pages", market_item.get("admin_pages", [])),
        "actions": (local_item or {}).get("actions", market_item.get("actions", [])),
        "publisher": {
            "name": str(publisher.get("name") or (local_item or {}).get("author") or "").strip(),
            "url": str(publisher.get("url") or (local_item or {}).get("homepage") or "").strip(),
            "verified": bool(publisher.get("verified", False) or market_item.get("verified", False)),
        },
        "compatibility": {
            "backend": str(compatibility.get("backend") or "fastapi").strip(),
            "frontend": str(compatibility.get("frontend") or "vue").strip(),
            "min_app_version": str(compatibility.get("min_app_version") or "1.0.0").strip(),
            "max_app_version": str(compatibility.get("max_app_version") or "").strip(),
        },
        "delivery": {
            "type": str(delivery.get("type") or ("builtin" if spec else "catalog")).strip(),
            "entry_mode": str(delivery.get("entry_mode") or "local").strip(),
            "install_strategy": install_strategy,
            "runtime_type": runtime_type,
            "entry_url": str(delivery.get("entry_url") or "").strip(),
        },
    }


def list_market_plugins(db: Session, settings: Settings) -> list[dict[str, Any]]:
    local_items = list_plugins_with_state(db, settings)
    local_map = {item["plugin_id"]: item for item in local_items}
    records = {item.plugin_id: item for item in db.query(PluginInstall).all()}

    market_items = load_market_catalog(settings)
    if not market_items:
        return local_items

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for market_item in market_items:
        plugin_id = str(market_item.get("plugin_id") or "").strip()
        if not plugin_id:
            continue
        seen.add(plugin_id)
        merged.append(_merge_market_with_local(market_item, local_map.get(plugin_id), records.get(plugin_id)))

    for plugin_id, local_item in local_map.items():
        if plugin_id in seen:
            continue
        merged.append(_merge_market_with_local(local_item, local_item, records.get(plugin_id)))

    return sorted(
        merged,
        key=lambda item: (
            0 if item.get("featured") else 1,
            0 if item.get("verified") else 1,
            str(item.get("name") or "").lower(),
        ),
    )
