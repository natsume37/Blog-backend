from dataclasses import asdict
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.plugin import PluginInstall
from app.services.plugins.base import PluginSpec
from app.services.plugins.builtin.ai_image_plugin import AI_IMAGE_PLUGIN
from app.services.plugins.builtin.ai_plugin import AI_PLUGIN
from app.services.plugins.builtin.wechat_official import WECHAT_PLUGIN
from app.services.plugins.storage import get_plugin_record


_REGISTRY: dict[str, PluginSpec] = {
    AI_IMAGE_PLUGIN.plugin_id: AI_IMAGE_PLUGIN,
    AI_PLUGIN.plugin_id: AI_PLUGIN,
    WECHAT_PLUGIN.plugin_id: WECHAT_PLUGIN,
}


def list_plugin_specs() -> list[PluginSpec]:
    return list(_REGISTRY.values())


def get_plugin_spec(plugin_id: str) -> PluginSpec | None:
    return _REGISTRY.get(plugin_id)


def _ensure_auto_installed_plugins(db: Session, settings: Settings) -> None:
    changed = False
    for spec in _REGISTRY.values():
        if not spec.auto_install:
            continue
        record = get_plugin_record(db, spec.plugin_id)
        if record:
            continue
        enabled = spec.default_enabled(db, settings) if spec.default_enabled else False
        db.add(PluginInstall(
            plugin_id=spec.plugin_id,
            name=spec.name,
            version=spec.version,
            description=spec.description,
            category=spec.category,
            source=spec.source,
            is_installed=True,
            is_enabled=bool(enabled),
        ))
        changed = True
    if changed:
        db.commit()


def install_plugin(db: Session, plugin_id: str, settings: Settings) -> PluginInstall:
    spec = get_plugin_spec(plugin_id)
    if not spec:
        raise KeyError(plugin_id)
    record = get_plugin_record(db, plugin_id)
    if record:
        record.is_installed = True
        record.version = spec.version
        record.name = spec.name
        record.description = spec.description
        record.category = spec.category
        record.source = spec.source
    else:
        record = PluginInstall(
            plugin_id=spec.plugin_id,
            name=spec.name,
            version=spec.version,
            description=spec.description,
            category=spec.category,
            source=spec.source,
            is_installed=True,
            is_enabled=False,
        )
        db.add(record)
    db.commit()
    db.refresh(record)
    return record


def set_plugin_enabled(db: Session, plugin_id: str, enabled: bool, settings: Settings) -> PluginInstall:
    spec = get_plugin_spec(plugin_id)
    if not spec:
        raise KeyError(plugin_id)
    record = get_plugin_record(db, plugin_id)
    if not record:
        record = install_plugin(db, plugin_id, settings)
    record.is_installed = True
    record.is_enabled = enabled
    db.commit()
    db.refresh(record)
    return record


def is_plugin_enabled(db: Session, plugin_id: str, settings: Settings) -> bool:
    _ensure_auto_installed_plugins(db, settings)
    record = get_plugin_record(db, plugin_id)
    return bool(record and record.is_installed and record.is_enabled)


def list_plugins_with_state(db: Session, settings: Settings) -> list[dict[str, Any]]:
    _ensure_auto_installed_plugins(db, settings)
    records = {
        item.plugin_id: item
        for item in db.query(PluginInstall).all()
    }
    items: list[dict[str, Any]] = []
    for spec in _REGISTRY.values():
        record = records.get(spec.plugin_id)
        items.append(_serialize_plugin_spec(spec, record))
    return items


def get_plugin_with_state(db: Session, plugin_id: str, settings: Settings) -> dict[str, Any]:
    _ensure_auto_installed_plugins(db, settings)
    spec = get_plugin_spec(plugin_id)
    if not spec:
        raise KeyError(plugin_id)
    record = get_plugin_record(db, plugin_id)
    return _serialize_plugin_spec(spec, record)


def _serialize_plugin_spec(spec: PluginSpec, record: PluginInstall | None) -> dict[str, Any]:
    return {
        "plugin_id": spec.plugin_id,
        "name": spec.name,
        "version": spec.version,
        "latest_version": spec.version,
        "installed_version": spec.version if record and record.is_installed else "",
        "description": spec.description,
        "summary": spec.description,
        "category": spec.category,
        "source": spec.source,
        "icon": spec.icon,
        "author": spec.author,
        "homepage": spec.homepage,
        "docs_url": spec.docs_url,
        "repo_url": spec.repository_url,
        "support_url": spec.support_url,
        "issues_url": spec.issues_url,
        "license": spec.license,
        "pricing": "free",
        "published_at": "",
        "manifest_url": "",
        "changelog_url": "",
        "source_repo": spec.repository_url,
        "keywords": list(spec.keywords),
        "tags": list(spec.tags),
        "features": list(spec.features),
        "capabilities": list(spec.capabilities),
        "permissions": list(spec.permissions),
        "builtin": True,
        "marketplace": False,
        "official": spec.source == "official",
        "verified": spec.verified or spec.source == "official",
        "featured": spec.featured,
        "installable": True,
        "activatable": True,
        "installed": bool(record.is_installed) if record else False,
        "enabled": bool(record.is_enabled) if record else False,
        "status": (
            "enabled"
            if record and record.is_installed and record.is_enabled
            else "installed"
            if record and record.is_installed
            else "available"
        ),
        "auto_install": spec.auto_install,
        "compatibility": {
            "backend": "fastapi",
            "frontend": "vue",
            "min_app_version": spec.min_app_version,
            "max_app_version": spec.max_app_version,
        },
        "delivery": {
            "type": "builtin",
            "entry_mode": "local",
            "install_strategy": spec.install_strategy,
            "runtime_type": spec.runtime_type,
            "entry_url": "",
        },
        "publisher": {
            "name": spec.publisher or spec.author,
            "url": spec.homepage,
            "verified": spec.verified or spec.source == "official",
        },
        "screenshots": [{"label": "", "url": item} for item in spec.screenshots],
        "settings_schema": [asdict(item) for item in spec.settings_schema],
        "admin_pages": [asdict(item) for item in spec.admin_pages],
        "actions": [asdict(item) for item in spec.actions],
    }
