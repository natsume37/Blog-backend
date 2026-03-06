import json
from datetime import datetime
from typing import Any
from urllib import request as urllib_request

from app.core.config import Settings
from app.schemas.ai import AIDraftRequest, AISummaryRequest


def _build_payload(data: AIDraftRequest) -> dict[str, Any]:
    keyword_text = "、".join(data.keywords) if data.keywords else "无"
    outline_text = "\n".join(f"- {item}" for item in data.outline) if data.outline else "- 背景\n- 核心观点\n- 实践步骤\n- 总结"

    system_prompt = (
        "你是资深中文技术内容编辑。"
        "请输出 JSON，不要输出 markdown 代码块。"
        "JSON 字段必须包含: title, summary, content_markdown, tags_suggestion。"
        "其中 content_markdown 必须是可直接发布的 Markdown 正文。"
    )
    user_prompt = (
        f"主题: {data.topic}\n"
        f"风格: {data.style}\n"
        f"语气: {data.tone}\n"
        f"语言: {data.language}\n"
        f"目标字数: {data.target_words}\n"
        f"关键词: {keyword_text}\n"
        f"大纲:\n{outline_text}\n"
        f"已有上下文:\n{data.existing_context or '无'}\n"
        f"是否需要摘要: {'是' if data.include_summary else '否'}\n"
    )
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.6,
    }


def _fallback_draft(data: AIDraftRequest, settings: Settings) -> dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d")
    tags = data.keywords[:3] if data.keywords else ["AI", "内容生产", "自动化"]
    summary = f"围绕「{data.topic}」的实践指南，覆盖背景、方案拆解与落地步骤。"
    content = f"""# {data.topic}

> 生成时间：{now}

## 背景与目标
本文聚焦 **{data.topic}**，目标是在可扩展架构下完成可持续迭代。

## 核心设计
1. 解耦内容生成与发布流程，形成可替换接口层。
2. 建立统一卡片化 UI 规范，减少页面重复实现。
3. 通过配置驱动 AI 服务，避免模型厂商绑定。

## 落地步骤
### 1. 统一 API 能力
- 约定 AI 草稿接口请求/响应结构。
- 在前端编辑器中保留人工校验与二次编辑能力。

### 2. 建立组件资产
- 以可复用 `UiCard` 组件收敛视觉和交互。
- 逐步替换页面中的散落容器样式。

### 3. 上线与演进
- 先灰度启用 AI 草稿能力，再逐步接入发布工作流。
- 增加审校、风险检测和发布审批节点。

## 总结
通过「配置化 AI 服务 + 组件化前端 + 解耦发布流程」，可以在保证可维护性的前提下持续扩展发布能力。
"""
    return {
        "title": data.topic,
        "summary": summary if data.include_summary else "",
        "content_markdown": content,
        "tags_suggestion": tags,
        "provider": settings.AI_PROVIDER,
        "model": settings.AI_MODEL,
    }


def generate_article_draft(data: AIDraftRequest, settings: Settings) -> dict[str, Any]:
    if not settings.is_ai_configured:
        return _fallback_draft(data, settings)

    payload = _build_payload(data)
    payload["model"] = settings.AI_MODEL
    body = json.dumps(payload).encode("utf-8")
    endpoint = f"{settings.AI_BASE_URL.rstrip('/')}/chat/completions"
    req = urllib_request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.AI_API_KEY}",
        },
    )
    with urllib_request.urlopen(req, timeout=settings.AI_TIMEOUT_SECONDS) as resp:
        raw = resp.read().decode("utf-8")
        data_json = json.loads(raw)
    content = (
        data_json.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    parsed = json.loads(content)
    return {
        "title": parsed.get("title") or data.topic,
        "summary": parsed.get("summary") or "",
        "content_markdown": parsed.get("content_markdown") or "",
        "tags_suggestion": parsed.get("tags_suggestion") or [],
        "provider": settings.AI_PROVIDER,
        "model": settings.AI_MODEL,
    }


def _strip_markdown(text: str) -> str:
    # 粗略清理 markdown 标记，保证 fallback 场景可读
    cleaned = text.replace("`", "").replace("*", "").replace("#", "")
    cleaned = cleaned.replace(">", "").replace("-", " ").replace("_", " ")
    return " ".join(cleaned.split())


def _fallback_summary(data: AISummaryRequest, settings: Settings) -> dict[str, Any]:
    plain = _strip_markdown(data.content_markdown)
    summary = plain[: data.max_length].strip()
    if len(plain) > data.max_length:
        summary += "..."
    return {
        "summary": summary or (data.title[: data.max_length] if data.title else "暂无摘要"),
        "provider": settings.AI_PROVIDER,
        "model": settings.AI_MODEL,
    }


def generate_article_summary(data: AISummaryRequest, settings: Settings) -> dict[str, Any]:
    if not settings.is_ai_configured:
        return _fallback_summary(data, settings)

    system_prompt = (
        "你是资深中文技术编辑。"
        "请输出 JSON，不要输出 markdown 代码块。"
        "JSON 字段必须包含: summary。"
    )
    user_prompt = (
        f"标题: {data.title or '无'}\n"
        f"风格: {data.style}\n"
        f"摘要最大长度: {data.max_length} 字\n"
        f"正文:\n{data.content_markdown}\n"
    )
    payload = {
        "model": settings.AI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
    }
    body = json.dumps(payload).encode("utf-8")
    endpoint = f"{settings.AI_BASE_URL.rstrip('/')}/chat/completions"
    req = urllib_request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.AI_API_KEY}",
        },
    )
    with urllib_request.urlopen(req, timeout=settings.AI_TIMEOUT_SECONDS) as resp:
        raw = resp.read().decode("utf-8")
        data_json = json.loads(raw)
    content = (
        data_json.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    parsed = json.loads(content)
    summary = (parsed.get("summary") or "").strip()
    if len(summary) > data.max_length:
        summary = summary[: data.max_length].rstrip() + "..."
    return {
        "summary": summary or _fallback_summary(data, settings)["summary"],
        "provider": settings.AI_PROVIDER,
        "model": settings.AI_MODEL,
    }
