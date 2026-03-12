from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.plugins.base import PluginSpec


NEWSNOW_PLUGIN_ID = "newsnow-realtime"
NEWSNOW_ENTRY_URL = "https://newsnow.busiyi.world/c/realtime"


def load_newsnow_settings(_db: Session, _settings: Settings) -> dict[str, Any]:
    return {}


def save_newsnow_settings(_db: Session, _payload: dict[str, Any], _settings: Settings) -> dict[str, Any]:
    return {}


def call_newsnow_action(_action: str, _payload: dict[str, Any], _db: Session, _settings: Settings) -> dict[str, Any]:
    raise KeyError("newsnow-realtime has no custom actions")


NEWSNOW_PLUGIN = PluginSpec(
    plugin_id=NEWSNOW_PLUGIN_ID,
    name="NewsNow 实时新闻",
    version="0.1.0",
    description="启用后在博客前台导航展示“博客 / 新闻”子菜单，并把新闻入口接入聚合实时新闻页。",
    category="content",
    source="official",
    settings_schema=[],
    admin_pages=[],
    actions=[],
    get_settings=load_newsnow_settings,
    save_settings=save_newsnow_settings,
    call_action=call_newsnow_action,
    icon="DataBoard",
    author="Martin",
    publisher="natsume37",
    homepage="https://martin88.xyz",
    docs_url=NEWSNOW_ENTRY_URL,
    repository_url="https://github.com/ourongxing/newsnow",
    support_url="https://github.com/natsume37/Blog-backend/issues",
    license="MIT",
    verified=True,
    featured=True,
    install_strategy="builtin-toggle",
    runtime_type="builtin",
    features=["前台导航扩展", "实时新闻入口", "博客与新闻切换"],
    keywords=["news", "realtime", "navigation", "homepage"],
    tags=["content", "navigation", "official"],
    capabilities=["public_navigation", "external_news_page"],
    permissions=[],
    screenshots=[],
    auto_install=False,
)
