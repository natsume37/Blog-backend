from typing import Any

from sqlalchemy.orm import Session

from app.models.plugin import PluginInstall, PluginSetting


def get_plugin_record(db: Session, plugin_id: str) -> PluginInstall | None:
    return db.query(PluginInstall).filter(PluginInstall.plugin_id == plugin_id).first()


def get_plugin_settings_map(db: Session, plugin_id: str) -> dict[str, str]:
    rows = db.query(PluginSetting).filter(PluginSetting.plugin_id == plugin_id).all()
    return {item.key: item.value or "" for item in rows}


def save_plugin_settings_map(db: Session, plugin_id: str, values: dict[str, Any]) -> dict[str, str]:
    saved: dict[str, str] = {}
    for key, raw_value in values.items():
        value = "" if raw_value is None else str(raw_value)
        row = db.query(PluginSetting).filter(
            PluginSetting.plugin_id == plugin_id,
            PluginSetting.key == key,
        ).first()
        if not row:
            row = PluginSetting(plugin_id=plugin_id, key=key, value=value)
            db.add(row)
        else:
            row.value = value
        saved[key] = value
    return saved
