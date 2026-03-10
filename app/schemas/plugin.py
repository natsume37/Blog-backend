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


class PluginActionResponse(BaseModel):
    name: str
    label: str
    description: str = ""


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
