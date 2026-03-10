import json
import re
from typing import Any

from app.core.config import Settings
from app.services.ai_common import extract_json_dict, request_chat_completion
from app.services.mcp_tools.base import MCPToolSpec


FIELD_NAMES = [
    "name",
    "url",
    "logo",
    "description",
    "group_name",
    "contact",
    "reciprocal_url",
    "site_color",
]


def _clean_text(value: Any, max_length: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]


def _normalize_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        if raw.startswith("www."):
            raw = f"https://{raw}"
        elif re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/[^\s]*)?$", raw):
            raw = f"https://{raw}"
    return raw[:500]


def _extract_first(patterns: list[str], lines: list[str]) -> str:
    for line in lines:
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return ""


def _extract_urls(raw_text: str) -> list[str]:
    url_pattern = re.compile(
        r"(https?://[^\s<>\"]+|www\.[^\s<>\"]+|(?<!@)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s<>\"]*)?)"
    )
    values: list[str] = []
    for match in url_pattern.finditer(raw_text):
        value = _normalize_url(match.group(1))
        if value and value not in values:
            values.append(value)
    return values


def _looks_like_logo(url: str) -> bool:
    lower = url.lower()
    return any(lower.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".svg", ".webp", ".ico", ".gif")) or any(
        token in lower for token in ("logo", "avatar", "icon", "favicon")
    )


def _extract_contact(raw_text: str) -> str:
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", raw_text, flags=re.IGNORECASE)
    if email_match:
        return email_match.group(0)

    qq_match = re.search(r"(?:QQ|qq)\s*[:：]?\s*([0-9]{5,12})", raw_text)
    if qq_match:
        return f"QQ {qq_match.group(1)}"

    wx_match = re.search(r"(?:微信|wx|wechat)\s*[:：]?\s*([a-zA-Z0-9_-]{4,30})", raw_text, flags=re.IGNORECASE)
    if wx_match:
        return f"微信 {wx_match.group(1)}"

    return ""


def _heuristic_parse(raw_text: str, default_group: str) -> dict[str, str]:
    lines = [line.strip(" -*•\t") for line in re.split(r"[\r\n]+", raw_text) if line.strip()]
    urls = _extract_urls(raw_text)
    markdown_link = re.search(r"\[([^\]]{1,100})\]\((https?://[^)]+)\)", raw_text)
    theme_color = re.search(r"#[0-9a-fA-F]{3,6}", raw_text)

    result = {
        "name": "",
        "url": "",
        "logo": "",
        "description": "",
        "group_name": default_group,
        "contact": "",
        "reciprocal_url": "",
        "site_color": theme_color.group(0) if theme_color else "",
    }

    if markdown_link:
        result["name"] = markdown_link.group(1).strip()
        result["url"] = _normalize_url(markdown_link.group(2))

    result["name"] = result["name"] or _clean_text(_extract_first([
        r"(?:站点名称|网站名称|博客名称|名称|站名|title|name)\s*[:：]\s*(.+)",
    ], lines), 100)
    result["url"] = result["url"] or _normalize_url(_extract_first([
        r"(?:站点链接|网站链接|博客地址|网站地址|网址|站点地址|site|url)\s*[:：]\s*(\S+)",
    ], lines))
    result["logo"] = _normalize_url(_extract_first([
        r"(?:logo|图标|头像|icon|favicon)\s*[:：]\s*(\S+)",
    ], lines))
    result["description"] = _clean_text(_extract_first([
        r"(?:站点简介|简介|描述|description|desc)\s*[:：]\s*(.+)",
    ], lines), 255)
    result["group_name"] = _clean_text(_extract_first([
        r"(?:分组|分类|group|category|类型)\s*[:：]\s*(.+)",
    ], lines), 50) or default_group
    result["contact"] = _clean_text(_extract_first([
        r"(?:联系(?:方式)?|contact|邮箱|email|qq|微信|wechat)\s*[:：]\s*(.+)",
    ], lines), 120)
    result["reciprocal_url"] = _normalize_url(_extract_first([
        r"(?:互链(?:地址|页面)?|友链(?:地址|页面)?|reciprocal(?:_url)?|friend(?:-|\s)?link)\s*[:：]\s*(\S+)",
    ], lines))

    if not result["contact"]:
        result["contact"] = _extract_contact(raw_text)

    if not result["url"]:
        non_logo_urls = [url for url in urls if not _looks_like_logo(url)]
        result["url"] = non_logo_urls[0] if non_logo_urls else ""

    if not result["logo"]:
        logo_urls = [url for url in urls if _looks_like_logo(url)]
        result["logo"] = logo_urls[0] if logo_urls else ""

    if not result["reciprocal_url"] and len(urls) > 1:
        for candidate in urls:
            if candidate != result["url"] and not _looks_like_logo(candidate):
                result["reciprocal_url"] = candidate
                break

    if not result["name"]:
        for line in lines[:4]:
            if len(line) <= 60 and "http" not in line and "www." not in line and "：" not in line and ":" not in line:
                result["name"] = _clean_text(line, 100)
                break

    if not result["description"]:
        for line in lines:
            if 12 <= len(line) <= 160 and line != result["name"] and result["url"] not in line:
                result["description"] = _clean_text(line, 255)
                break

    return result


def _merge_fields(primary: dict[str, Any], fallback: dict[str, str], default_group: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    for key in FIELD_NAMES:
        value = primary.get(key)
        if key in {"url", "logo", "reciprocal_url"}:
            merged[key] = _normalize_url(value) or fallback.get(key, "")
        elif key == "group_name":
            merged[key] = _clean_text(value, 50) or fallback.get(key, "") or default_group
        elif key == "description":
            merged[key] = _clean_text(value, 255) or fallback.get(key, "")
        elif key == "contact":
            merged[key] = _clean_text(value, 120) or fallback.get(key, "")
        elif key == "site_color":
            cleaned = _clean_text(value, 20)
            merged[key] = cleaned or fallback.get(key, "")
        else:
            merged[key] = _clean_text(value, 100 if key == "name" else 500) or fallback.get(key, "")
    return merged


def _ai_parse(raw_text: str, heuristics: dict[str, str], default_group: str, settings: Settings) -> tuple[dict[str, Any], str]:
    if not settings.is_ai_configured:
        return {}, "fallback"

    system_prompt = (
        "你是一个 MCP 工具插件，负责从用户粘贴的友链资料中提取结构化字段。"
        "只输出 JSON，不要输出 markdown 代码块，不要解释。"
        "必须返回字段: name, url, logo, description, group_name, contact, reciprocal_url, site_color, confidence, reasoning。"
        "未知字段返回空字符串。confidence 只能是 low、medium、high。"
        "不要臆造站点链接、Logo 或联系方式。group_name 允许根据内容语义做合理归类，否则返回默认值。"
    )
    user_prompt = (
        f"原始内容:\n{raw_text}\n\n"
        f"默认分组: {default_group}\n"
        f"启发式预解析结果:\n{json.dumps(heuristics, ensure_ascii=False)}\n"
    )
    content = request_chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        settings,
        temperature=0.1,
        force_json=True,
    )
    parsed = extract_json_dict(content) or {}
    if not isinstance(parsed, dict):
        return {}, "fallback"
    return parsed, "hybrid"


def _build_summary(fields: dict[str, str], filled_fields: list[str], warnings: list[str], confidence: str, reasoning: str) -> str:
    filled_text = "、".join(filled_fields) if filled_fields else "无"
    warning_text = f"；提示：{'；'.join(warnings)}" if warnings else ""
    confidence_text = confidence or "medium"
    reasoning_text = f"；依据：{reasoning}" if reasoning else ""
    return f"已识别字段：{filled_text}；置信度：{confidence_text}{warning_text}{reasoning_text}"


def run_friend_link_parser(arguments: dict[str, Any], settings: Settings) -> dict[str, Any]:
    raw_text = _clean_text(arguments.get("raw_text") or arguments.get("content"), 8000)
    if not raw_text:
        raise ValueError("raw_text 不能为空")

    context = arguments.get("context") if isinstance(arguments.get("context"), dict) else {}
    default_group = _clean_text(context.get("default_group"), 50) or "推荐站点"

    heuristics = _heuristic_parse(raw_text, default_group)
    ai_result, mode = _ai_parse(raw_text, heuristics, default_group, settings)
    fields = _merge_fields(ai_result, heuristics, default_group)

    filled_fields = [key for key in FIELD_NAMES if fields.get(key)]
    missing_fields = [key for key in FIELD_NAMES if not fields.get(key)]
    warnings: list[str] = []
    if not fields["name"]:
        warnings.append("未识别到站点名称")
    if not fields["url"]:
        warnings.append("未识别到站点链接")
    if not fields["contact"]:
        warnings.append("未识别到联系方式，提交前建议手动补充")

    confidence = _clean_text(ai_result.get("confidence"), 20) or ("medium" if len(filled_fields) >= 4 else "low")
    reasoning = _clean_text(ai_result.get("reasoning"), 180)

    return {
        "mode": mode,
        "structuredContent": {
            "fields": fields,
            "filled_fields": filled_fields,
            "missing_fields": missing_fields,
            "warnings": warnings,
            "confidence": confidence,
            "reasoning": reasoning,
        },
        "content": [
            {
                "type": "text",
                "text": _build_summary(fields, filled_fields, warnings, confidence, reasoning),
            }
        ],
    }


TOOL_SPEC = MCPToolSpec(
    name="friend_link_parser",
    description="从站点介绍、友链模板或任意粘贴文本中提取友链申请表字段，并返回可直接回填表单的结构化结果。",
    input_schema={
        "type": "object",
        "properties": {
            "raw_text": {
                "type": "string",
                "description": "用户粘贴的原始友链资料、站点介绍或任意文本。",
            },
            "context": {
                "type": "object",
                "description": "可选上下文，例如默认分组、当前页面信息等。",
            },
        },
        "required": ["raw_text"],
    },
    public=True,
    handler=run_friend_link_parser,
)
