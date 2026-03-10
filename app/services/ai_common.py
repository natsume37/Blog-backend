import json
import re
from typing import Any
from urllib import request as urllib_request

from app.core.config import Settings


def supports_json_output(settings: Settings) -> bool:
    provider = (settings.AI_PROVIDER or "").lower()
    base_url = (settings.AI_BASE_URL or "").lower()
    return (
        "deepseek" in provider
        or "openai" in provider
        or "deepseek" in base_url
        or "openai" in base_url
    )


def attach_json_output(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    if supports_json_output(settings):
        payload["response_format"] = {"type": "json_object"}
    return payload


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def extract_json_dict(raw_text: str) -> dict[str, Any] | None:
    text = (raw_text or "").strip()
    if not text:
        return None

    fence = re.match(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", text, flags=re.IGNORECASE | re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def request_chat_completion(
    messages: list[dict[str, str]],
    settings: Settings,
    *,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    force_json: bool = False,
) -> str:
    payload: dict[str, Any] = {
        "model": settings.AI_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if force_json:
        payload = attach_json_output(payload, settings)

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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

    return content_to_text(
        data_json.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
