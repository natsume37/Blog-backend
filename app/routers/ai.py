import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_current_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.ai import (
    AIDraftRequest,
    AIDraftResponse,
    AISummaryRequest,
    AISummaryResponse,
    AIConfig,
    AIConfigTestResult,
    MCPToolCallRequest,
    MCPToolCallResponse,
    MCPToolContentItem,
    MCPToolDefinition,
)
from app.schemas.common import ResponseModel
from app.services.ai_article import generate_article_draft, generate_article_summary
from app.services.mcp_tools import call_public_tool, list_public_tools
from app.services.plugins import is_plugin_enabled
from app.services.plugins.builtin.ai_plugin import (
    AI_PLUGIN_ID,
    friendly_ai_error,
    resolve_ai_runtime_settings,
    save_ai_plugin_settings,
    test_ai_runtime,
)
from app.utils.audit import record_admin_action


router = APIRouter(prefix="/ai", tags=["AI"])
logger = logging.getLogger(__name__)


@router.get("/config", response_model=ResponseModel[AIConfig])
def get_ai_config(
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    runtime = resolve_ai_runtime_settings(
        db,
        settings,
        plugin_enabled=is_plugin_enabled(db, AI_PLUGIN_ID, settings),
    )
    data = AIConfig(
        ai_enabled=runtime.AI_ENABLED,
        ai_provider=runtime.AI_PROVIDER,
        ai_base_url=runtime.AI_BASE_URL or "",
        ai_api_key=runtime.AI_API_KEY or "",
        ai_model=runtime.AI_MODEL,
        ai_timeout_seconds=runtime.AI_TIMEOUT_SECONDS,
    )
    return ResponseModel(code=200, data=data)


@router.put("/config", response_model=ResponseModel[AIConfig])
def update_ai_config(
    payload: AIConfig,
    request: Request,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    save_ai_plugin_settings(db, payload.model_dump(), settings)
    db.commit()
    runtime = resolve_ai_runtime_settings(
        db,
        settings,
        plugin_enabled=is_plugin_enabled(db, AI_PLUGIN_ID, settings),
    )
    data = AIConfig(
        ai_enabled=runtime.AI_ENABLED,
        ai_provider=runtime.AI_PROVIDER,
        ai_base_url=runtime.AI_BASE_URL or "",
        ai_api_key=runtime.AI_API_KEY or "",
        ai_model=runtime.AI_MODEL,
        ai_timeout_seconds=runtime.AI_TIMEOUT_SECONDS,
    )
    record_admin_action(
        user=current_user,
        action="ai.config.update",
        target_type="ai_config",
        target_id="global",
        description="更新 AI 配置",
        request=request,
        extra={"provider": data.ai_provider, "model": data.ai_model, "enabled": data.ai_enabled},
    )
    return ResponseModel(code=200, msg="AI 配置已更新", data=data)


@router.post("/test", response_model=ResponseModel[AIConfigTestResult])
def test_ai_config(
    request: Request,
    payload: AIConfig | None = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        runtime = resolve_ai_runtime_settings(
            db,
            settings,
            plugin_enabled=is_plugin_enabled(db, AI_PLUGIN_ID, settings),
        )
        if payload is not None:
            runtime = runtime.model_copy(update={
                "AI_ENABLED": payload.ai_enabled,
                "AI_PROVIDER": payload.ai_provider.strip() or runtime.AI_PROVIDER,
                "AI_BASE_URL": payload.ai_base_url.strip() or None,
                "AI_API_KEY": payload.ai_api_key.strip() or None,
                "AI_MODEL": payload.ai_model.strip() or runtime.AI_MODEL,
                "AI_TIMEOUT_SECONDS": max(1, int(payload.ai_timeout_seconds)),
            })
        result = AIConfigTestResult(**test_ai_runtime(runtime))
        record_admin_action(
            user=current_user,
            action="ai.config.test",
            target_type="ai_config",
            target_id="global",
            description=f"AI 连通性测试{'成功' if result.ok else '失败'}",
            request=request,
            extra={"provider": result.provider, "model": result.model, "latency_ms": result.latency_ms, "ok": result.ok},
        )
        return ResponseModel(code=200 if result.ok else 400, msg=result.message, data=result)
    except Exception as exc:
        msg = friendly_ai_error(exc)
        logger.error("Test AI config failed: %s", exc, exc_info=True)
        record_admin_action(
            user=current_user,
            action="ai.config.test",
            target_type="ai_config",
            target_id="global",
            description="AI 连通性测试失败",
            request=request,
            extra={"error": str(exc)},
        )
        return ResponseModel(
            code=500,
            msg=msg,
            data=AIConfigTestResult(
                ok=False,
                message=msg,
                provider=(payload.ai_provider if payload else settings.AI_PROVIDER),
                model=(payload.ai_model if payload else settings.AI_MODEL),
                latency_ms=0,
            ),
        )


@router.post("/article-draft", response_model=ResponseModel[AIDraftResponse])
def create_article_draft(
    payload: AIDraftRequest,
    _: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    """生成文章草稿（管理员）"""
    try:
        runtime = resolve_ai_runtime_settings(
            db,
            settings,
            plugin_enabled=is_plugin_enabled(db, AI_PLUGIN_ID, settings),
        )
        if not runtime.AI_ENABLED:
            return ResponseModel(code=400, msg="AI 插件未启用或未完成配置")
        data = generate_article_draft(payload, runtime)
        if not data.get("content_markdown"):
            return ResponseModel(code=502, msg="AI 返回内容为空")
        return ResponseModel(code=200, msg="生成成功", data=AIDraftResponse(**data))
    except Exception as exc:
        logger.error("Generate AI draft failed: %s", exc, exc_info=True)
        return ResponseModel(code=500, msg=friendly_ai_error(exc))


@router.post("/article-summary", response_model=ResponseModel[AISummaryResponse])
def create_article_summary(
    payload: AISummaryRequest,
    _: User = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    """生成文章摘要（管理员）"""
    try:
        runtime = resolve_ai_runtime_settings(
            db,
            settings,
            plugin_enabled=is_plugin_enabled(db, AI_PLUGIN_ID, settings),
        )
        if not runtime.AI_ENABLED:
            return ResponseModel(code=400, msg="AI 插件未启用或未完成配置")
        data = generate_article_summary(payload, runtime)
        if not data.get("summary"):
            return ResponseModel(code=502, msg="AI 返回摘要为空")
        return ResponseModel(code=200, msg="生成成功", data=AISummaryResponse(**data))
    except Exception as exc:
        logger.error("Generate AI summary failed: %s", exc, exc_info=True)
        return ResponseModel(code=500, msg=friendly_ai_error(exc))


@router.get("/mcp/tools", response_model=ResponseModel[list[MCPToolDefinition]])
def list_mcp_tools():
    tools = [
        MCPToolDefinition(
            name=tool.name,
            description=tool.description,
            inputSchema=tool.input_schema,
        )
        for tool in list_public_tools()
    ]
    return ResponseModel(code=200, msg="获取成功", data=tools)


@router.post("/mcp/call", response_model=ResponseModel[MCPToolCallResponse])
def call_mcp_tool(
    payload: MCPToolCallRequest,
    _: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        runtime = resolve_ai_runtime_settings(
            db,
            settings,
            plugin_enabled=is_plugin_enabled(db, AI_PLUGIN_ID, settings),
        )
        result = call_public_tool(payload.name, payload.arguments or {}, runtime)
        data = MCPToolCallResponse(
            name=payload.name,
            mode=result.get("mode") or ("ai" if runtime.is_ai_configured else "fallback"),
            provider=runtime.AI_PROVIDER,
            model=runtime.AI_MODEL,
            structuredContent=result.get("structuredContent") or {},
            content=[
                MCPToolContentItem(
                    type=item.get("type", "text"),
                    text=item.get("text", ""),
                )
                for item in (result.get("content") or [])
                if isinstance(item, dict)
            ],
            isError=bool(result.get("isError", False)),
        )
        return ResponseModel(code=200, msg="工具调用成功", data=data)
    except KeyError:
        return ResponseModel(code=404, msg=f"工具不存在: {payload.name}")
    except Exception as exc:
        logger.error("Call MCP tool failed: %s", exc, exc_info=True)
        return ResponseModel(
            code=500,
            msg=friendly_ai_error(exc),
            data=MCPToolCallResponse(
                name=payload.name,
                mode="error",
                provider=settings.AI_PROVIDER,
                model=settings.AI_MODEL,
                structuredContent={},
                content=[MCPToolContentItem(type="text", text=friendly_ai_error(exc))],
                isError=True,
            ),
        )
