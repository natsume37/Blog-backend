import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import get_current_admin
from app.models.user import User
from app.schemas.common import ResponseModel
from app.schemas.plugin import (
    PluginActionPayload,
    PluginActionResultResponse,
    PluginItemResponse,
    PluginSettingsPayload,
    PluginSettingsResponse,
)
from app.services.plugins import (
    get_plugin_spec,
    get_plugin_with_state,
    install_plugin,
    list_plugins_with_state,
    set_plugin_enabled,
)
from app.services.plugins.builtin.wechat_official import _friendly_wechat_error
from app.utils.audit import record_admin_action


router = APIRouter(prefix="/plugins", tags=["插件"])
logger = logging.getLogger(__name__)


def _friendly_plugin_error(exc: Exception) -> str:
    from app.services.plugins.builtin.ai_plugin import friendly_ai_error

    message = str(exc or "").strip()
    if "WeChat" in message or "微信" in message:
        return _friendly_wechat_error(exc)
    if "AI" in message or "Base URL" in message:
        return friendly_ai_error(exc)
    return message or "插件操作失败"


@router.get("/market", response_model=ResponseModel[list[PluginItemResponse]])
def get_plugin_market(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    return ResponseModel(code=200, msg="获取成功", data=list_plugins_with_state(db, settings))


@router.get("", response_model=ResponseModel[list[PluginItemResponse]])
def get_admin_plugins(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    return ResponseModel(code=200, msg="获取成功", data=list_plugins_with_state(db, settings))


@router.post("/{plugin_id}/install", response_model=ResponseModel[PluginItemResponse])
def install_admin_plugin(
    plugin_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    try:
        install_plugin(db, plugin_id, settings)
        item = get_plugin_with_state(db, plugin_id, settings)
        record_admin_action(
            user=current_user,
            action="plugin.install",
            target_type="plugin",
            target_id=plugin_id,
            description=f"安装插件: {plugin_id}",
            request=request,
        )
        return ResponseModel(code=200, msg="插件已安装", data=item)
    except KeyError:
        return ResponseModel(code=404, msg=f"插件不存在: {plugin_id}")


@router.post("/{plugin_id}/enable", response_model=ResponseModel[PluginItemResponse])
def enable_admin_plugin(
    plugin_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    try:
        set_plugin_enabled(db, plugin_id, True, settings)
        item = get_plugin_with_state(db, plugin_id, settings)
        record_admin_action(
            user=current_user,
            action="plugin.enable",
            target_type="plugin",
            target_id=plugin_id,
            description=f"启用插件: {plugin_id}",
            request=request,
        )
        return ResponseModel(code=200, msg="插件已启用", data=item)
    except KeyError:
        return ResponseModel(code=404, msg=f"插件不存在: {plugin_id}")


@router.post("/{plugin_id}/disable", response_model=ResponseModel[PluginItemResponse])
def disable_admin_plugin(
    plugin_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    try:
        set_plugin_enabled(db, plugin_id, False, settings)
        item = get_plugin_with_state(db, plugin_id, settings)
        record_admin_action(
            user=current_user,
            action="plugin.disable",
            target_type="plugin",
            target_id=plugin_id,
            description=f"停用插件: {plugin_id}",
            request=request,
        )
        return ResponseModel(code=200, msg="插件已停用", data=item)
    except KeyError:
        return ResponseModel(code=404, msg=f"插件不存在: {plugin_id}")


@router.get("/{plugin_id}/settings", response_model=ResponseModel[PluginSettingsResponse])
def get_plugin_settings(
    plugin_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    spec = get_plugin_spec(plugin_id)
    if not spec:
        return ResponseModel(code=404, msg=f"插件不存在: {plugin_id}")
    values = spec.get_settings(db, settings)
    return ResponseModel(code=200, msg="获取成功", data=PluginSettingsResponse(plugin_id=plugin_id, values=values))


@router.put("/{plugin_id}/settings", response_model=ResponseModel[PluginSettingsResponse])
def update_plugin_settings(
    plugin_id: str,
    payload: PluginSettingsPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    spec = get_plugin_spec(plugin_id)
    if not spec:
        return ResponseModel(code=404, msg=f"插件不存在: {plugin_id}")
    try:
        values = spec.save_settings(db, payload.values or {}, settings)
        db.commit()
        record_admin_action(
            user=current_user,
            action="plugin.settings.update",
            target_type="plugin",
            target_id=plugin_id,
            description=f"更新插件配置: {plugin_id}",
            request=request,
        )
        return ResponseModel(code=200, msg="插件配置已更新", data=PluginSettingsResponse(plugin_id=plugin_id, values=values))
    except Exception as exc:
        db.rollback()
        logger.error("Update plugin settings failed: %s", exc, exc_info=True)
        return ResponseModel(code=500, msg=_friendly_plugin_error(exc))


@router.post("/{plugin_id}/actions/{action}", response_model=ResponseModel[PluginActionResultResponse])
def call_plugin_action(
    plugin_id: str,
    action: str,
    payload: PluginActionPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
):
    spec = get_plugin_spec(plugin_id)
    if not spec:
        return ResponseModel(code=404, msg=f"插件不存在: {plugin_id}")
    item = get_plugin_with_state(db, plugin_id, settings)
    if action != "test_connection" and not item["enabled"]:
        return ResponseModel(code=400, msg="请先启用插件，再执行该动作")
    try:
        result = spec.call_action(action, payload.payload or {}, db, settings)
        record_admin_action(
            user=current_user,
            action=f"plugin.action.{action}",
            target_type="plugin",
            target_id=plugin_id,
            description=f"执行插件动作: {plugin_id}/{action}",
            request=request,
            extra={"payload": payload.payload},
        )
        return ResponseModel(
            code=200,
            msg="插件动作执行成功",
            data=PluginActionResultResponse(plugin_id=plugin_id, action=action, result=result),
        )
    except KeyError:
        return ResponseModel(code=404, msg=f"插件动作不存在: {action}")
    except Exception as exc:
        logger.error("Call plugin action failed: %s", exc, exc_info=True)
        return ResponseModel(code=500, msg=_friendly_plugin_error(exc))
