from typing import Any

from pydantic import BaseModel, Field


class PluginSettingOptionResponse(BaseModel):
    label: str
    value: str


class PluginSettingFieldResponse(BaseModel):
    key: str
    label: str
    type: str
    description: str = ""
    required: bool = False
    secret: bool = False
    placeholder: str = ""
    default: Any = None
    options: list[PluginSettingOptionResponse] = Field(default_factory=list)


class PluginAdminPageResponse(BaseModel):
    path: str
    route_name: str
    title: str
    menu_label: str
    component_key: str
    icon: str = "Grid"
    render_mode: str = "local"
    entry_url: str = ""


class PluginActionResponse(BaseModel):
    name: str
    label: str
    description: str = ""


class PluginCompatibilityResponse(BaseModel):
    backend: str = ""
    frontend: str = ""
    min_app_version: str = ""
    max_app_version: str = ""


class PluginDeliveryResponse(BaseModel):
    type: str = "builtin"
    entry_mode: str = "local"
    install_strategy: str = "builtin-toggle"
    runtime_type: str = "builtin"
    entry_url: str = ""


class PluginPublisherResponse(BaseModel):
    name: str = ""
    url: str = ""
    verified: bool = False


class PluginScreenshotResponse(BaseModel):
    label: str = ""
    url: str = ""


class PluginItemResponse(BaseModel):
    plugin_id: str
    name: str
    version: str
    description: str
    category: str
    source: str
    installed: bool
    enabled: bool
    auto_install: bool = False
    builtin: bool = False
    marketplace: bool = False
    official: bool = False
    verified: bool = False
    featured: bool = False
    installable: bool = False
    activatable: bool = False
    upgrade_available: bool = False
    status: str = "available"
    summary: str = ""
    author: str = ""
    icon: str = "Grid"
    latest_version: str = ""
    installed_version: str = ""
    license: str = ""
    pricing: str = ""
    published_at: str = ""
    homepage: str = ""
    docs_url: str = ""
    repo_url: str = ""
    support_url: str = ""
    issues_url: str = ""
    readme_url: str = ""
    changelog_url: str = ""
    manifest_url: str = ""
    source_repo: str = ""
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    compatibility: PluginCompatibilityResponse = Field(default_factory=PluginCompatibilityResponse)
    delivery: PluginDeliveryResponse = Field(default_factory=PluginDeliveryResponse)
    publisher: PluginPublisherResponse = Field(default_factory=PluginPublisherResponse)
    screenshots: list[PluginScreenshotResponse] = Field(default_factory=list)
    settings_schema: list[PluginSettingFieldResponse] = Field(default_factory=list)
    admin_pages: list[PluginAdminPageResponse] = Field(default_factory=list)
    actions: list[PluginActionResponse] = Field(default_factory=list)


class PluginSettingsPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


class PluginSettingsResponse(BaseModel):
    plugin_id: str
    values: dict[str, Any] = Field(default_factory=dict)


class PluginActionPayload(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class PluginActionResultResponse(BaseModel):
    plugin_id: str
    action: str
    result: dict[str, Any] = Field(default_factory=dict)
