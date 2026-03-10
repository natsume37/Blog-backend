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
    render_mode: str = "local"
    entry_url: str = ""
    script_url: str = ""
    layout: str = "panel"


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
    icon: str = "Grid"
    author: str = ""
    publisher: str = ""
    homepage: str = ""
    docs_url: str = ""
    repository_url: str = ""
    support_url: str = ""
    issues_url: str = ""
    license: str = ""
    verified: bool = False
    featured: bool = False
    install_strategy: str = "builtin"
    runtime_type: str = "builtin"
    min_app_version: str = "1.0.0"
    max_app_version: str = ""
    features: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    auto_install: bool = False
    default_enabled: PluginEnabledDefault | None = None
