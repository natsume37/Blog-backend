from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.config import Settings


PluginActionHandler = Callable[[str, dict[str, Any], Session, Settings], dict[str, Any]]
PluginSettingsLoader = Callable[[Session, Settings], dict[str, Any]]
PluginSettingsSaver = Callable[[Session, dict[str, Any], Settings], dict[str, Any]]
PluginEnabledDefault = Callable[[Session, Settings], bool]


@dataclass(frozen=True)
class PluginSettingOption:
    label: str
    value: str


@dataclass(frozen=True)
class PluginSettingField:
    key: str
    label: str
    type: str
    description: str = ""
    required: bool = False
    secret: bool = False
    placeholder: str = ""
    default: Any = None
    options: list[PluginSettingOption] = field(default_factory=list)


@dataclass(frozen=True)
class PluginAdminPage:
    path: str
    route_name: str
    title: str
    menu_label: str
    component_key: str
    icon: str = "Grid"


@dataclass(frozen=True)
class PluginActionSpec:
    name: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class PluginSpec:
    plugin_id: str
    name: str
    version: str
    description: str
    category: str
    source: str
    settings_schema: list[PluginSettingField]
    admin_pages: list[PluginAdminPage]
    actions: list[PluginActionSpec]
    get_settings: PluginSettingsLoader
    save_settings: PluginSettingsSaver
    call_action: PluginActionHandler
    auto_install: bool = False
    default_enabled: PluginEnabledDefault | None = None
