import html
import json
import mimetypes
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any
from urllib import parse as urlparse
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.article import Article
from app.models.user import User
from app.models.wechat_plugin import WechatBroadcastTask, WechatQrCodeRecord
from app.services.plugins.base import (
    PluginActionSpec,
    PluginAdminPage,
    PluginSettingField,
    PluginSettingOption,
    PluginSpec,
)
from app.services.plugins.storage import get_plugin_settings_map, save_plugin_settings_map
from app.utils.qiniu import normalize_remote_url


WECHAT_PLUGIN_ID = "wechat-official-account"
_IMG_TAG_RE = re.compile(r'(<img\b[^>]*?\ssrc=")([^"]+)(")', re.IGNORECASE)
_MAX_WECHAT_PAGE_SIZE = 20

_FREEPUBLISH_STATUS_MAP = {
    0: ("published", "已发布"),
    1: ("publishing", "发布中"),
    2: ("failed", "原创校验失败"),
    3: ("failed", "发布失败"),
    4: ("reviewing", "平台审核中"),
    5: ("failed", "审核驳回"),
    6: ("deleted", "已删除"),
}

_MASS_STATUS_MAP = {
    "SEND_SUCCESS": ("published", "群发成功"),
    "SENDING": ("sending", "群发中"),
    "SEND_FAIL": ("failed", "群发失败"),
    "DELETE": ("deleted", "已删除"),
    "DRAFT": ("draft", "草稿中"),
}


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    if raw in {"true", "1", "yes", "y", "on"}:
        return True
    if raw in {"false", "0", "no", "n", "off"}:
        return False
    return default


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _string(value: Any) -> str:
    return str(value or "").strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: str) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _isoformat(value: datetime | None) -> str:
    if not value:
        return ""
    return value.isoformat(timespec="seconds")


def _utcnow() -> datetime:
    return datetime.utcnow()


def _clamp_page_size(size: Any, default: int = 10) -> int:
    parsed = _parse_int(size, default)
    return max(1, min(_MAX_WECHAT_PAGE_SIZE, parsed))


def _safe_response_json(resp) -> dict[str, Any]:
    raw = resp.read().decode("utf-8", errors="ignore")
    payload = json.loads(raw or "{}")
    if not isinstance(payload, dict):
        raise RuntimeError("微信接口返回格式异常")
    errcode = int(payload.get("errcode", 0) or 0)
    if errcode != 0:
        errmsg = str(payload.get("errmsg", ""))
        raise RuntimeError(f"WeChat API error {errcode}: {errmsg}")
    return payload


def _request_json(url: str, *, data: dict[str, Any] | None = None, timeout: int = 20) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(url, data=body, method="POST" if data is not None else "GET", headers=headers)
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        return _safe_response_json(resp)


def _encode_multipart(file_field: str, filename: str, file_bytes: bytes, content_type: str) -> tuple[bytes, str]:
    boundary = f"----BlogPluginBoundary{uuid.uuid4().hex}"
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(parts), boundary


def _post_multipart(
    url: str,
    *,
    file_field: str,
    filename: str,
    file_bytes: bytes,
    content_type: str,
    timeout: int = 30,
) -> dict[str, Any]:
    body, boundary = _encode_multipart(file_field, filename, file_bytes, content_type)
    req = urllib_request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "Accept": "application/json",
        },
    )
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        return _safe_response_json(resp)


def _download_binary(url: str, timeout: int = 30) -> tuple[bytes, str, str]:
    normalized_url = normalize_remote_url(url)
    req = urllib_request.Request(normalized_url, headers={"User-Agent": "BlogPlugin/1.0"})
    with urllib_request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get_content_type() or "application/octet-stream"
        data = resp.read()
    parsed = urlparse.urlparse(normalized_url)
    filename = os.path.basename(urlparse.unquote(parsed.path)) or f"wechat-{uuid.uuid4().hex}"
    if "." not in filename:
        ext = mimetypes.guess_extension(content_type) or ".bin"
        filename = f"{filename}{ext}"
    return data, content_type, filename


def _is_remote_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _absolute_article_url(base_url: str, article: Article) -> str:
    root = (base_url or "").rstrip("/")
    if not root:
        return ""
    if root.endswith("/article"):
        return f"{root}/{article.id}"
    return f"{root}/article/{article.id}"


def _load_markdown_converter():
    try:
        from markdown import markdown as render_markdown  # type: ignore

        def _render(text: str) -> str:
            return render_markdown(
                text or "",
                extensions=["extra", "sane_lists", "tables", "fenced_code", "nl2br"],
                output_format="html5",
            )

        return _render
    except Exception:
        return None


def _fallback_markdown_to_html(text: str) -> str:
    blocks: list[str] = []
    lines = (text or "").splitlines()
    in_code = False
    code_lines: list[str] = []
    para_lines: list[str] = []

    def flush_para() -> None:
        if not para_lines:
            return
        escaped = " ".join(html.escape(item.strip()) for item in para_lines if item.strip())
        if escaped:
            blocks.append(f"<p>{escaped}</p>")
        para_lines.clear()

    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                blocks.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                flush_para()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue

        stripped = line.strip()
        if not stripped:
            flush_para()
            continue
        if stripped.startswith("### "):
            flush_para()
            blocks.append(f"<h3>{html.escape(stripped[4:])}</h3>")
            continue
        if stripped.startswith("## "):
            flush_para()
            blocks.append(f"<h2>{html.escape(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# "):
            flush_para()
            blocks.append(f"<h1>{html.escape(stripped[2:])}</h1>")
            continue
        para_lines.append(line)

    flush_para()
    if in_code and code_lines:
        blocks.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(blocks)


def _render_article_html(markdown_text: str) -> str:
    renderer = _load_markdown_converter()
    if renderer:
        return renderer(markdown_text or "")
    return _fallback_markdown_to_html(markdown_text or "")


def _exchange_access_token(app_id: str, app_secret: str, timeout: int = 20) -> str:
    query = urlparse.urlencode({
        "grant_type": "client_credential",
        "appid": app_id,
        "secret": app_secret,
    })
    url = f"https://api.weixin.qq.com/cgi-bin/token?{query}"
    payload = _request_json(url, timeout=timeout)
    access_token = _string(payload.get("access_token"))
    if not access_token:
        raise RuntimeError("未获取到 access_token")
    return access_token


def _upload_cover_as_material(access_token: str, image_url: str, timeout: int = 30) -> str:
    file_bytes, content_type, filename = _download_binary(image_url, timeout=timeout)
    payload = _post_multipart(
        f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image",
        file_field="media",
        filename=filename,
        file_bytes=file_bytes,
        content_type=content_type,
        timeout=timeout,
    )
    media_id = _string(payload.get("media_id"))
    if not media_id:
        raise RuntimeError("上传封面到微信素材库失败，未返回 media_id")
    return media_id


def _upload_material_image(access_token: str, image_url: str, timeout: int = 30) -> dict[str, Any]:
    file_bytes, content_type, filename = _download_binary(image_url, timeout=timeout)
    payload = _post_multipart(
        f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image",
        file_field="media",
        filename=filename,
        file_bytes=file_bytes,
        content_type=content_type,
        timeout=timeout,
    )
    return {
        "media_id": _string(payload.get("media_id")),
        "url": _string(payload.get("url")),
        "name": _string(payload.get("name")) or filename,
        "raw": payload,
    }


def _upload_content_image(access_token: str, image_url: str, timeout: int = 30) -> str:
    file_bytes, content_type, filename = _download_binary(image_url, timeout=timeout)
    payload = _post_multipart(
        f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={access_token}",
        file_field="media",
        filename=filename,
        file_bytes=file_bytes,
        content_type=content_type,
        timeout=timeout,
    )
    result_url = _string(payload.get("url"))
    if not result_url:
        raise RuntimeError("上传正文图片失败，未返回 url")
    return result_url


def _rewrite_content_images(access_token: str, html_content: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        original_url = _string(match.group(2))
        if not _is_remote_url(original_url):
            return match.group(0)
        uploaded_url = _upload_content_image(access_token, original_url)
        return f'{match.group(1)}{uploaded_url}{match.group(3)}'

    return _IMG_TAG_RE.sub(_replace, html_content or "")


def _load_article_for_publish(db: Session, article_id: int) -> Article:
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise ValueError("文章不存在")
    return article


def _resolve_author_name(article: Article, db: Session, configured_author: str) -> str:
    if configured_author.strip():
        return configured_author.strip()
    author = db.query(User).filter(User.id == article.author_id).first()
    if author:
        return _string(author.nickname or author.username)
    return ""


def load_wechat_settings(db: Session, _: Settings) -> dict[str, Any]:
    values = get_plugin_settings_map(db, WECHAT_PLUGIN_ID)
    return {
        "app_id": values.get("app_id", ""),
        "app_secret": values.get("app_secret", ""),
        "author": values.get("author", ""),
        "publish_mode": values.get("publish_mode", "draft") or "draft",
        "content_source_url_base": values.get("content_source_url_base", ""),
        "fallback_thumb_media_id": values.get("fallback_thumb_media_id", ""),
        "need_open_comment": _parse_bool(values.get("need_open_comment", "true"), True),
        "only_fans_can_comment": _parse_bool(values.get("only_fans_can_comment", "false"), False),
        "preview_target_type": values.get("preview_target_type", "towxname") or "towxname",
        "preview_target_value": values.get("preview_target_value", ""),
        "send_ignore_reprint": _parse_bool(values.get("send_ignore_reprint", "false"), False),
        "default_tag_id": values.get("default_tag_id", ""),
    }


def save_wechat_settings(db: Session, payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    current = load_wechat_settings(db, settings)
    merged = {
        "app_id": _string(payload.get("app_id", current["app_id"])),
        "app_secret": _string(payload.get("app_secret", current["app_secret"])),
        "author": _string(payload.get("author", current["author"])),
        "publish_mode": _string(payload.get("publish_mode", current["publish_mode"])) or "draft",
        "content_source_url_base": _string(payload.get("content_source_url_base", current["content_source_url_base"])),
        "fallback_thumb_media_id": _string(payload.get("fallback_thumb_media_id", current["fallback_thumb_media_id"])),
        "need_open_comment": "true" if _parse_bool(payload.get("need_open_comment", current["need_open_comment"]), True) else "false",
        "only_fans_can_comment": "true" if _parse_bool(payload.get("only_fans_can_comment", current["only_fans_can_comment"]), False) else "false",
        "preview_target_type": _string(payload.get("preview_target_type", current["preview_target_type"])) or "towxname",
        "preview_target_value": _string(payload.get("preview_target_value", current["preview_target_value"])),
        "send_ignore_reprint": "true" if _parse_bool(payload.get("send_ignore_reprint", current["send_ignore_reprint"]), False) else "false",
        "default_tag_id": _string(payload.get("default_tag_id", current["default_tag_id"])),
    }
    save_plugin_settings_map(db, WECHAT_PLUGIN_ID, merged)
    return load_wechat_settings(db, settings)


def _ensure_wechat_ready(config: dict[str, Any]) -> None:
    if not _string(config.get("app_id")):
        raise ValueError("请先配置 AppID")
    if not _string(config.get("app_secret")):
        raise ValueError("请先配置 AppSecret")


def _build_wechat_article_payload(article: Article, db: Session, config: dict[str, Any], access_token: str) -> dict[str, Any]:
    source_url = _absolute_article_url(_string(config.get("content_source_url_base")), article)
    author_name = _resolve_author_name(article, db, _string(config.get("author")))
    html_content = _render_article_html(article.content or "")
    html_content = _rewrite_content_images(access_token, html_content)

    thumb_media_id = _string(config.get("fallback_thumb_media_id"))
    if article.cover and _is_remote_url(article.cover):
        thumb_media_id = _upload_cover_as_material(access_token, article.cover)
    if not thumb_media_id:
        raise ValueError("文章没有可用封面，且插件未配置 fallback_thumb_media_id")

    digest = _string(article.summary)
    return {
        "title": article.title or "",
        "author": author_name,
        "digest": digest,
        "content": html_content,
        "content_source_url": source_url,
        "thumb_media_id": thumb_media_id,
        "show_cover_pic": 1,
        "need_open_comment": 1 if _parse_bool(config.get("need_open_comment"), True) else 0,
        "only_fans_can_comment": 1 if _parse_bool(config.get("only_fans_can_comment"), False) else 0,
    }


def _create_draft(access_token: str, article_payload: dict[str, Any]) -> dict[str, Any]:
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}",
        data={"articles": [article_payload]},
        timeout=30,
    )


def _list_drafts(access_token: str, *, offset: int, count: int) -> dict[str, Any]:
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/draft/batchget?access_token={access_token}",
        data={"offset": offset, "count": count, "no_content": 0},
        timeout=30,
    )


def _get_draft(access_token: str, media_id: str) -> dict[str, Any]:
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/draft/get?access_token={access_token}",
        data={"media_id": media_id},
        timeout=30,
    )


def _delete_draft(access_token: str, media_id: str) -> dict[str, Any]:
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/draft/delete?access_token={access_token}",
        data={"media_id": media_id},
        timeout=20,
    )


def _create_broadcast_media(access_token: str, articles: list[dict[str, Any]]) -> dict[str, Any]:
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/media/uploadnews?access_token={access_token}",
        data={"articles": articles},
        timeout=30,
    )


def _submit_publish(access_token: str, media_id: str) -> dict[str, Any]:
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/freepublish/submit?access_token={access_token}",
        data={"media_id": media_id},
        timeout=30,
    )


def _query_publish_status(access_token: str, publish_id: str) -> dict[str, Any]:
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/freepublish/get?access_token={access_token}",
        data={"publish_id": publish_id},
        timeout=20,
    )


def _preview_broadcast(access_token: str, media_id: str, target_type: str, target_value: str) -> dict[str, Any]:
    field_name = "touser" if target_type == "touser" else "towxname"
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/message/mass/preview?access_token={access_token}",
        data={
            field_name: target_value,
            "mpnews": {"media_id": media_id},
            "msgtype": "mpnews",
        },
        timeout=30,
    )


def _send_broadcast(access_token: str, media_id: str, *, is_to_all: bool, tag_id: int | None, send_ignore_reprint: bool) -> dict[str, Any]:
    filter_payload: dict[str, Any] = {"is_to_all": bool(is_to_all)}
    if not is_to_all and tag_id is not None:
        filter_payload["tag_id"] = tag_id
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/message/mass/sendall?access_token={access_token}",
        data={
            "filter": filter_payload,
            "mpnews": {"media_id": media_id},
            "msgtype": "mpnews",
            "send_ignore_reprint": 1 if send_ignore_reprint else 0,
        },
        timeout=30,
    )


def _query_mass_status(access_token: str, msg_id: str) -> dict[str, Any]:
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/message/mass/get?access_token={access_token}",
        data={"msg_id": msg_id},
        timeout=20,
    )


def _list_materials(access_token: str, *, offset: int, count: int) -> dict[str, Any]:
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/material/batchget_material?access_token={access_token}",
        data={"type": "image", "offset": offset, "count": count},
        timeout=30,
    )


def _delete_material(access_token: str, media_id: str) -> dict[str, Any]:
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/material/del_material?access_token={access_token}",
        data={"media_id": media_id},
        timeout=20,
    )


def _create_qrcode(access_token: str, action_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/qrcode/create?access_token={access_token}",
        data=payload,
        timeout=30,
    )


def _mass_status_from_payload(payload: dict[str, Any]) -> tuple[str, str]:
    raw = _string(payload.get("msg_status")).upper()
    if not raw:
        return "unknown", "未知状态"
    return _MASS_STATUS_MAP.get(raw, (raw.lower(), raw))


def _freepublish_status_from_payload(payload: dict[str, Any]) -> tuple[str, str]:
    raw_status = payload.get("publish_status", payload.get("status"))
    code = _parse_int(raw_status, -1)
    if code in _FREEPUBLISH_STATUS_MAP:
        return _FREEPUBLISH_STATUS_MAP[code]
    return "unknown", f"状态 {raw_status}"


def _is_finished_status(status: str) -> bool:
    return status in {"published", "failed", "deleted", "preview_sent", "completed"}


def _serialize_draft_item(item: dict[str, Any]) -> dict[str, Any]:
    content = item.get("content") if isinstance(item.get("content"), dict) else {}
    news_items = content.get("news_item") if isinstance(content.get("news_item"), list) else []
    first_item = news_items[0] if news_items and isinstance(news_items[0], dict) else {}
    return {
        "media_id": _string(item.get("media_id")),
        "article_count": len(news_items),
        "title": _string(first_item.get("title")),
        "author": _string(first_item.get("author")),
        "digest": _string(first_item.get("digest")),
        "thumb_url": _string(first_item.get("thumb_url")),
        "update_time": _parse_int(item.get("update_time"), 0),
        "created_at": _parse_int(item.get("create_time"), 0),
        "news_items": news_items,
    }


def _serialize_material_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "media_id": _string(item.get("media_id")),
        "name": _string(item.get("name")),
        "url": _string(item.get("url")),
        "update_time": _parse_int(item.get("update_time"), 0),
    }


def _serialize_task(task: WechatBroadcastTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "task_type": task.task_type,
        "source_type": task.source_type,
        "article_id": task.article_id,
        "title": task.title or "",
        "draft_media_id": task.draft_media_id or "",
        "broadcast_media_id": task.broadcast_media_id or "",
        "publish_id": task.publish_id or "",
        "msg_id": task.msg_id or "",
        "preview_target": task.preview_target or "",
        "audience_type": task.audience_type,
        "audience_value": task.audience_value or "",
        "status": task.status,
        "status_text": task.status_text or "",
        "request_payload": _json_loads(task.request_payload or ""),
        "response_payload": _json_loads(task.response_payload or ""),
        "result_payload": _json_loads(task.result_payload or ""),
        "created_by": task.created_by,
        "created_at": _isoformat(task.created_at),
        "updated_at": _isoformat(task.updated_at),
        "finished_at": _isoformat(task.finished_at),
    }


def _serialize_qrcode(record: WechatQrCodeRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "name": record.name or "",
        "action_name": record.action_name,
        "scene_type": record.scene_type,
        "scene_value": record.scene_value,
        "ticket": record.ticket,
        "url": record.url or "",
        "image_url": record.image_url or "",
        "expire_seconds": record.expire_seconds,
        "expires_at": _isoformat(record.expires_at),
        "created_by": record.created_by,
        "created_at": _isoformat(record.created_at),
    }


def _create_task(
    db: Session,
    *,
    task_type: str,
    source_type: str,
    article_id: int | None,
    title: str,
    audience_type: str,
    audience_value: str,
    created_by: int | None,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    draft_media_id: str = "",
    broadcast_media_id: str = "",
    publish_id: str = "",
    msg_id: str = "",
    preview_target: str = "",
    status: str = "pending",
    status_text: str = "",
    result_payload: dict[str, Any] | None = None,
    finished_at: datetime | None = None,
) -> WechatBroadcastTask:
    task = WechatBroadcastTask(
        task_type=task_type,
        source_type=source_type,
        article_id=article_id,
        title=title,
        draft_media_id=draft_media_id or None,
        broadcast_media_id=broadcast_media_id or None,
        publish_id=publish_id or None,
        msg_id=msg_id or None,
        preview_target=preview_target or "",
        audience_type=audience_type,
        audience_value=audience_value or "",
        status=status,
        status_text=status_text,
        request_payload=_json_dumps(request_payload),
        response_payload=_json_dumps(response_payload),
        result_payload=_json_dumps(result_payload or {}),
        created_by=created_by,
        finished_at=finished_at,
    )
    db.add(task)
    db.flush()
    return task


def _update_task_status(task: WechatBroadcastTask, payload: dict[str, Any]) -> WechatBroadcastTask:
    if task.task_type == "freepublish":
        status, status_text = _freepublish_status_from_payload(payload)
    elif task.task_type == "mass_send":
        status, status_text = _mass_status_from_payload(payload)
    else:
        status = task.status
        status_text = task.status_text
    task.status = status
    task.status_text = status_text
    task.result_payload = _json_dumps(payload)
    if _is_finished_status(status):
        task.finished_at = _utcnow()
    return task


def _build_articles_from_draft_payload(draft_payload: dict[str, Any]) -> list[dict[str, Any]]:
    news_item = draft_payload.get("news_item")
    if not isinstance(news_item, list):
        content = draft_payload.get("content") if isinstance(draft_payload.get("content"), dict) else {}
        news_item = content.get("news_item")
    if not isinstance(news_item, list) or not news_item:
        raise ValueError("未从草稿中获取到图文内容")
    articles: list[dict[str, Any]] = []
    for item in news_item:
        if isinstance(item, dict):
            articles.append(item)
    if not articles:
        raise ValueError("未从草稿中获取到图文内容")
    return articles


def _resolve_content_articles(
    db: Session,
    config: dict[str, Any],
    access_token: str,
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    source_type = _string(payload.get("source_type")) or "article"
    if source_type == "draft":
        draft_media_id = _string(payload.get("draft_media_id"))
        if not draft_media_id:
            raise ValueError("请选择微信草稿")
        draft_payload = _get_draft(access_token, draft_media_id)
        articles = _build_articles_from_draft_payload(draft_payload)
        first_title = _string(articles[0].get("title")) if articles else ""
        return articles, {"source_type": "draft", "draft_media_id": draft_media_id, "title": first_title}, draft_payload

    article_id = _parse_int(payload.get("article_id"), 0)
    if article_id <= 0:
        raise ValueError("请选择有效文章")
    article = _load_article_for_publish(db, article_id)
    article_payload = _build_wechat_article_payload(article, db, config, access_token)
    return [article_payload], {"source_type": "article", "article_id": article.id, "title": article.title or ""}, {"article_id": article.id}


def _query_tasks(db: Session, payload: dict[str, Any]) -> tuple[list[WechatBroadcastTask], int]:
    page = max(1, _parse_int(payload.get("page"), 1))
    size = max(1, min(50, _parse_int(payload.get("size"), 10)))
    query = db.query(WechatBroadcastTask)
    task_type = _string(payload.get("task_type"))
    status = _string(payload.get("status"))
    if task_type:
        query = query.filter(WechatBroadcastTask.task_type == task_type)
    if status:
        query = query.filter(WechatBroadcastTask.status == status)
    total = query.count()
    records = (
        query.order_by(WechatBroadcastTask.created_at.desc(), WechatBroadcastTask.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return records, total


def _query_qrcode_records(db: Session, payload: dict[str, Any]) -> tuple[list[WechatQrCodeRecord], int]:
    page = max(1, _parse_int(payload.get("page"), 1))
    size = max(1, min(50, _parse_int(payload.get("size"), 10)))
    query = db.query(WechatQrCodeRecord)
    total = query.count()
    records = (
        query.order_by(WechatQrCodeRecord.created_at.desc(), WechatQrCodeRecord.id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return records, total


def _build_dashboard_summary(db: Session) -> dict[str, Any]:
    recent_tasks = (
        db.query(WechatBroadcastTask)
        .order_by(WechatBroadcastTask.created_at.desc(), WechatBroadcastTask.id.desc())
        .limit(6)
        .all()
    )
    recent_qrcodes = (
        db.query(WechatQrCodeRecord)
        .order_by(WechatQrCodeRecord.created_at.desc(), WechatQrCodeRecord.id.desc())
        .limit(4)
        .all()
    )
    return {
        "counts": {
            "drafts": db.query(WechatBroadcastTask).filter(WechatBroadcastTask.task_type == "draft").count(),
            "freepublish": db.query(WechatBroadcastTask).filter(WechatBroadcastTask.task_type == "freepublish").count(),
            "mass_send": db.query(WechatBroadcastTask).filter(WechatBroadcastTask.task_type == "mass_send").count(),
            "preview": db.query(WechatBroadcastTask).filter(WechatBroadcastTask.task_type == "preview").count(),
            "qrcodes": db.query(WechatQrCodeRecord).count(),
        },
        "recent_tasks": [_serialize_task(item) for item in recent_tasks],
        "recent_qrcodes": [_serialize_qrcode(item) for item in recent_qrcodes],
    }


def _friendly_wechat_error(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"微信公众号接口返回错误（HTTP {exc.code}）"
    if isinstance(exc, URLError):
        reason = str(getattr(exc, "reason", exc))
        return f"微信公众号接口网络异常：{reason}"
    text = str(exc).strip()
    return text or "微信公众号操作失败"


def wechat_call_action(action: str, payload: dict[str, Any], db: Session, settings: Settings) -> dict[str, Any]:
    config = load_wechat_settings(db, settings)
    actor_id = _parse_int(payload.get("_actor_id"), 0) or None

    if action == "test_connection":
        _ensure_wechat_ready(config)
        token = _exchange_access_token(config["app_id"], config["app_secret"])
        return {"ok": True, "message": "微信公众号连接成功", "access_token_preview": f"{token[:8]}..."}

    if action == "dashboard_summary":
        return {
            "ok": True,
            "message": "获取控制台概览成功",
            "config_ready": bool(_string(config.get("app_id")) and _string(config.get("app_secret"))),
            "summary": _build_dashboard_summary(db),
        }

    if action in {"publish_article", "publish"}:
        config = {
            **config,
            "author": _string(payload.get("author", config["author"])),
            "publish_mode": _string(payload.get("publish_mode", config["publish_mode"])) or "draft",
            "need_open_comment": _parse_bool(payload.get("need_open_comment", config["need_open_comment"]), True),
            "only_fans_can_comment": _parse_bool(payload.get("only_fans_can_comment", config["only_fans_can_comment"]), False),
        }
        _ensure_wechat_ready(config)
        article_id = _parse_int(payload.get("article_id"), 0)
        if article_id <= 0:
            raise ValueError("article_id 非法")
        article = _load_article_for_publish(db, article_id)
        access_token = _exchange_access_token(config["app_id"], config["app_secret"])
        article_payload = _build_wechat_article_payload(article, db, config, access_token)
        draft_result = _create_draft(access_token, article_payload)
        media_id = _string(draft_result.get("media_id"))
        if not media_id:
            raise RuntimeError("草稿创建成功但未返回 media_id")

        publish_mode = _string(payload.get("publish_mode") or config["publish_mode"] or "draft")
        if publish_mode == "publish":
            publish_result = _submit_publish(access_token, media_id)
            publish_id = _string(publish_result.get("publish_id"))
            task = _create_task(
                db,
                task_type="freepublish",
                source_type="article",
                article_id=article.id,
                title=article.title or "",
                audience_type="freepublish",
                audience_value=media_id,
                created_by=actor_id,
                request_payload={
                    "article_id": article.id,
                    "publish_mode": "publish",
                    "author": config["author"],
                },
                response_payload=publish_result,
                draft_media_id=media_id,
                publish_id=publish_id,
                status="publishing",
                status_text="已进入发布队列",
            )
            return {
                "ok": True,
                "message": "文章已提交到微信公众号发布队列",
                "mode": "publish",
                "article_id": article.id,
                "title": article.title,
                "media_id": media_id,
                "publish_id": publish_id,
                "task": _serialize_task(task),
            }

        task = _create_task(
            db,
            task_type="draft",
            source_type="article",
            article_id=article.id,
            title=article.title or "",
            audience_type="draft",
            audience_value=media_id,
            created_by=actor_id,
            request_payload={"article_id": article.id, "publish_mode": "draft"},
            response_payload=draft_result,
            draft_media_id=media_id,
            status="draft",
            status_text="已保存到微信草稿箱",
            finished_at=_utcnow(),
        )
        return {
            "ok": True,
            "message": "文章已同步到微信公众号草稿箱",
            "mode": "draft",
            "article_id": article.id,
            "title": article.title,
            "media_id": media_id,
            "task": _serialize_task(task),
        }

    if action == "query_publish_status":
        _ensure_wechat_ready(config)
        publish_id = _string(payload.get("publish_id"))
        if not publish_id:
            raise ValueError("publish_id 不能为空")
        access_token = _exchange_access_token(config["app_id"], config["app_secret"])
        status_payload = _query_publish_status(access_token, publish_id)
        return {"ok": True, "message": "获取发布状态成功", "status": status_payload}

    if action == "list_drafts":
        _ensure_wechat_ready(config)
        page = max(1, _parse_int(payload.get("page"), 1))
        size = _clamp_page_size(payload.get("size"), 10)
        access_token = _exchange_access_token(config["app_id"], config["app_secret"])
        remote = _list_drafts(access_token, offset=(page - 1) * size, count=size)
        items = remote.get("item") if isinstance(remote.get("item"), list) else []
        return {
            "ok": True,
            "message": "获取微信草稿成功",
            "page": page,
            "size": size,
            "total": _parse_int(remote.get("total_count"), len(items)),
            "items": [_serialize_draft_item(item) for item in items if isinstance(item, dict)],
        }

    if action == "delete_draft":
        _ensure_wechat_ready(config)
        media_id = _string(payload.get("media_id"))
        if not media_id:
            raise ValueError("media_id 不能为空")
        access_token = _exchange_access_token(config["app_id"], config["app_secret"])
        _delete_draft(access_token, media_id)
        return {"ok": True, "message": "微信草稿已删除", "media_id": media_id}

    if action == "publish_draft":
        _ensure_wechat_ready(config)
        media_id = _string(payload.get("media_id"))
        if not media_id:
            raise ValueError("media_id 不能为空")
        access_token = _exchange_access_token(config["app_id"], config["app_secret"])
        publish_result = _submit_publish(access_token, media_id)
        publish_id = _string(publish_result.get("publish_id"))
        task = _create_task(
            db,
            task_type="freepublish",
            source_type="draft",
            article_id=None,
            title=_string(payload.get("title")),
            audience_type="freepublish",
            audience_value=media_id,
            created_by=actor_id,
            request_payload={"media_id": media_id},
            response_payload=publish_result,
            draft_media_id=media_id,
            publish_id=publish_id,
            status="publishing",
            status_text="草稿已提交发布",
        )
        return {
            "ok": True,
            "message": "微信草稿已提交发布",
            "publish_id": publish_id,
            "task": _serialize_task(task),
        }

    if action == "list_materials":
        _ensure_wechat_ready(config)
        page = max(1, _parse_int(payload.get("page"), 1))
        size = _clamp_page_size(payload.get("size"), 12)
        access_token = _exchange_access_token(config["app_id"], config["app_secret"])
        remote = _list_materials(access_token, offset=(page - 1) * size, count=size)
        items = remote.get("item") if isinstance(remote.get("item"), list) else []
        return {
            "ok": True,
            "message": "获取微信图库成功",
            "page": page,
            "size": size,
            "total": _parse_int(remote.get("total_count"), len(items)),
            "items": [_serialize_material_item(item) for item in items if isinstance(item, dict)],
        }

    if action == "upload_material_from_url":
        _ensure_wechat_ready(config)
        image_url = _string(payload.get("url") or payload.get("image_url") or payload.get("resource_url"))
        if not image_url:
            raise ValueError("请提供图片地址")
        access_token = _exchange_access_token(config["app_id"], config["app_secret"])
        result = _upload_material_image(access_token, image_url)
        return {
            "ok": True,
            "message": "图片已上传到微信图库",
            "item": {
                "media_id": result["media_id"],
                "name": result["name"],
                "url": result["url"],
            },
            "raw": result["raw"],
        }

    if action == "delete_material":
        _ensure_wechat_ready(config)
        media_id = _string(payload.get("media_id"))
        if not media_id:
            raise ValueError("media_id 不能为空")
        access_token = _exchange_access_token(config["app_id"], config["app_secret"])
        _delete_material(access_token, media_id)
        return {"ok": True, "message": "微信素材已删除", "media_id": media_id}

    if action in {"preview_broadcast", "send_broadcast"}:
        _ensure_wechat_ready(config)
        access_token = _exchange_access_token(config["app_id"], config["app_secret"])
        articles, source_meta, source_payload = _resolve_content_articles(db, config, access_token, payload)
        broadcast_media = _create_broadcast_media(access_token, articles)
        broadcast_media_id = _string(broadcast_media.get("media_id"))
        if not broadcast_media_id:
            raise RuntimeError("创建群发素材失败，未返回 media_id")

        if action == "preview_broadcast":
            target_type = _string(payload.get("target_type") or config.get("preview_target_type")) or "towxname"
            target_value = _string(payload.get("target_value") or config.get("preview_target_value"))
            if not target_value:
                raise ValueError("请填写预览接收目标")
            preview_result = _preview_broadcast(access_token, broadcast_media_id, target_type, target_value)
            task = _create_task(
                db,
                task_type="preview",
                source_type=source_meta["source_type"],
                article_id=source_meta.get("article_id"),
                title=_string(source_meta.get("title")),
                audience_type="preview",
                audience_value=target_type,
                created_by=actor_id,
                request_payload={
                    **source_meta,
                    "target_type": target_type,
                    "target_value": target_value,
                },
                response_payload=preview_result,
                broadcast_media_id=broadcast_media_id,
                preview_target=target_value,
                status="preview_sent",
                status_text="预览消息已发送",
                result_payload={"broadcast_media_id": broadcast_media_id, "source": source_payload},
                finished_at=_utcnow(),
            )
            return {
                "ok": True,
                "message": "预览消息已发送",
                "broadcast_media_id": broadcast_media_id,
                "task": _serialize_task(task),
            }

        audience_mode = _string(payload.get("audience_mode")) or "all"
        is_to_all = audience_mode != "tag"
        tag_id: int | None = None
        if not is_to_all:
            raw_tag_id = _string(payload.get("tag_id") or config.get("default_tag_id"))
            if not raw_tag_id:
                raise ValueError("按标签群发时必须提供 tag_id")
            tag_id = _parse_int(raw_tag_id, 0)
            if tag_id <= 0:
                raise ValueError("tag_id 非法")

        send_ignore_reprint = _parse_bool(payload.get("send_ignore_reprint", config.get("send_ignore_reprint")), False)
        send_result = _send_broadcast(
            access_token,
            broadcast_media_id,
            is_to_all=is_to_all,
            tag_id=tag_id,
            send_ignore_reprint=send_ignore_reprint,
        )
        msg_id = _string(send_result.get("msg_id"))
        task = _create_task(
            db,
            task_type="mass_send",
            source_type=source_meta["source_type"],
            article_id=source_meta.get("article_id"),
            title=_string(source_meta.get("title")),
            audience_type="all" if is_to_all else "tag",
            audience_value="" if is_to_all else str(tag_id),
            created_by=actor_id,
            request_payload={
                **source_meta,
                "audience_mode": audience_mode,
                "tag_id": tag_id,
                "send_ignore_reprint": send_ignore_reprint,
            },
            response_payload=send_result,
            broadcast_media_id=broadcast_media_id,
            msg_id=msg_id,
            status="sending",
            status_text="群发任务已提交",
            result_payload={"source": source_payload},
        )
        return {
            "ok": True,
            "message": "群发任务已提交",
            "msg_id": msg_id,
            "broadcast_media_id": broadcast_media_id,
            "task": _serialize_task(task),
        }

    if action == "list_tasks":
        records, total = _query_tasks(db, payload)
        return {
            "ok": True,
            "message": "获取任务列表成功",
            "page": max(1, _parse_int(payload.get("page"), 1)),
            "size": max(1, min(50, _parse_int(payload.get("size"), 10))),
            "total": total,
            "items": [_serialize_task(item) for item in records],
        }

    if action == "refresh_task_status":
        _ensure_wechat_ready(config)
        task_id = _parse_int(payload.get("task_id"), 0)
        if task_id <= 0:
            raise ValueError("task_id 非法")
        task = db.query(WechatBroadcastTask).filter(WechatBroadcastTask.id == task_id).first()
        if not task:
            raise ValueError("任务不存在")
        access_token = _exchange_access_token(config["app_id"], config["app_secret"])
        if task.task_type == "freepublish":
            if not _string(task.publish_id):
                raise ValueError("该任务没有 publish_id")
            status_payload = _query_publish_status(access_token, task.publish_id)
        elif task.task_type == "mass_send":
            if not _string(task.msg_id):
                raise ValueError("该任务没有 msg_id")
            status_payload = _query_mass_status(access_token, task.msg_id)
        else:
            return {
                "ok": True,
                "message": "该任务无需刷新状态",
                "task": _serialize_task(task),
            }
        _update_task_status(task, status_payload)
        db.flush()
        return {
            "ok": True,
            "message": "任务状态已刷新",
            "task": _serialize_task(task),
            "status_payload": status_payload,
        }

    if action == "create_qrcode":
        _ensure_wechat_ready(config)
        name = _string(payload.get("name"))
        qrcode_mode = _string(payload.get("mode")) or "temp"
        scene_type = _string(payload.get("scene_type")) or "str"
        scene_value = _string(payload.get("scene_value"))
        if not scene_value:
            raise ValueError("scene_value 不能为空")
        if scene_type == "int" and _parse_int(scene_value, 0) <= 0:
            raise ValueError("数字场景值必须是大于 0 的整数")
        expire_seconds = _parse_int(payload.get("expire_seconds"), 604800)
        if qrcode_mode == "permanent":
            action_name = "QR_LIMIT_STR_SCENE" if scene_type == "str" else "QR_LIMIT_SCENE"
        else:
            action_name = "QR_STR_SCENE" if scene_type == "str" else "QR_SCENE"
        scene_payload: dict[str, Any] = {"scene_str": scene_value} if scene_type == "str" else {"scene_id": _parse_int(scene_value, 0)}
        request_payload = {
            "action_name": action_name,
            "action_info": {"scene": scene_payload},
        }
        if not action_name.startswith("QR_LIMIT_"):
            request_payload["expire_seconds"] = max(60, min(2592000, expire_seconds))
        access_token = _exchange_access_token(config["app_id"], config["app_secret"])
        result = _create_qrcode(access_token, action_name, request_payload)
        ticket = _string(result.get("ticket"))
        if not ticket:
            raise RuntimeError("微信二维码创建成功但未返回 ticket")
        image_url = f"https://mp.weixin.qq.com/cgi-bin/showqrcode?ticket={urlparse.quote(ticket)}"
        expires_at = None
        if result.get("expire_seconds"):
            expires_at = _utcnow() + timedelta(seconds=_parse_int(result.get("expire_seconds"), expire_seconds))
        record = WechatQrCodeRecord(
            name=name,
            action_name=action_name,
            scene_type=scene_type,
            scene_value=scene_value,
            ticket=ticket,
            url=_string(result.get("url")),
            image_url=image_url,
            expire_seconds=_parse_int(result.get("expire_seconds"), expire_seconds) if result.get("expire_seconds") else None,
            expires_at=expires_at,
            request_payload=_json_dumps(request_payload),
            response_payload=_json_dumps(result),
            created_by=actor_id,
        )
        db.add(record)
        db.flush()
        return {
            "ok": True,
            "message": "二维码已生成",
            "record": _serialize_qrcode(record),
            "raw": result,
        }

    if action == "list_qrcodes":
        records, total = _query_qrcode_records(db, payload)
        return {
            "ok": True,
            "message": "获取二维码记录成功",
            "page": max(1, _parse_int(payload.get("page"), 1)),
            "size": max(1, min(50, _parse_int(payload.get("size"), 10))),
            "total": total,
            "items": [_serialize_qrcode(item) for item in records],
        }

    raise KeyError(action)


WECHAT_PLUGIN = PluginSpec(
    plugin_id=WECHAT_PLUGIN_ID,
    name="微信公众号工作台",
    version="2.0.0",
    description="提供公众号草稿、微信图库、预览发送、真群发、二维码和状态反馈的一体化工作台。",
    category="distribution",
    source="official",
    settings_schema=[
        PluginSettingField(key="app_id", label="AppID", type="text", required=True, placeholder="公众号 AppID"),
        PluginSettingField(key="app_secret", label="AppSecret", type="password", required=True, secret=True, placeholder="公众号 AppSecret"),
        PluginSettingField(key="author", label="默认作者", type="text", placeholder="为空时使用文章作者"),
        PluginSettingField(key="content_source_url_base", label="文章原文链接前缀", type="text", placeholder="例如 https://martin88.xyz/article"),
        PluginSettingField(
            key="publish_mode",
            label="默认文章同步模式",
            type="select",
            default="draft",
            options=[
                PluginSettingOption(label="仅保存为草稿", value="draft"),
                PluginSettingOption(label="创建草稿后直接提交发布", value="publish"),
            ],
        ),
        PluginSettingField(key="fallback_thumb_media_id", label="备用封面 Media ID", type="text", description="文章没有封面时使用。"),
        PluginSettingField(key="need_open_comment", label="开启评论", type="switch", default=True),
        PluginSettingField(key="only_fans_can_comment", label="仅粉丝可评论", type="switch", default=False),
        PluginSettingField(
            key="preview_target_type",
            label="默认预览目标类型",
            type="select",
            default="towxname",
            options=[
                PluginSettingOption(label="微信号", value="towxname"),
                PluginSettingOption(label="OpenID", value="touser"),
            ],
        ),
        PluginSettingField(key="preview_target_value", label="默认预览目标", type="text", placeholder="微信号或 OpenID"),
        PluginSettingField(key="default_tag_id", label="默认群发标签 ID", type="text", placeholder="按标签群发时使用"),
        PluginSettingField(key="send_ignore_reprint", label="忽略转载校验", type="switch", default=False),
    ],
    admin_pages=[
        PluginAdminPage(
            path="/admin/plugins/wechat-official-account/publisher",
            route_name="PluginWeChatOfficialAccountDashboard",
            title="公众号工作台",
            menu_label="公众号工作台",
            component_key="plugin.wechat.dashboard",
            icon="Promotion",
            layout="workspace",
        ),
        PluginAdminPage(
            path="/admin/plugins/wechat-official-account/drafts",
            route_name="PluginWeChatOfficialAccountDrafts",
            title="公众号草稿",
            menu_label="公众号草稿",
            component_key="plugin.wechat.drafts",
            icon="Document",
            layout="workspace",
        ),
        PluginAdminPage(
            path="/admin/plugins/wechat-official-account/media",
            route_name="PluginWeChatOfficialAccountMedia",
            title="微信图库",
            menu_label="微信图库",
            component_key="plugin.wechat.media",
            icon="PictureFilled",
            layout="workspace",
        ),
        PluginAdminPage(
            path="/admin/plugins/wechat-official-account/broadcast",
            route_name="PluginWeChatOfficialAccountBroadcast",
            title="群发中心",
            menu_label="群发中心",
            component_key="plugin.wechat.broadcast",
            icon="Connection",
            layout="workspace",
        ),
        PluginAdminPage(
            path="/admin/plugins/wechat-official-account/qrcodes",
            route_name="PluginWeChatOfficialAccountQrcodes",
            title="二维码",
            menu_label="二维码",
            component_key="plugin.wechat.qrcode",
            icon="Tickets",
            layout="workspace",
        ),
    ],
    actions=[
        PluginActionSpec(name="test_connection", label="测试连接", description="验证公众号凭证是否可用。"),
        PluginActionSpec(name="dashboard_summary", label="控制台概览", description="获取最近任务和二维码概览。"),
        PluginActionSpec(name="publish_article", label="同步文章", description="把站内文章同步到微信草稿或直接送审发布。"),
        PluginActionSpec(name="list_drafts", label="草稿列表", description="分页获取公众号草稿。"),
        PluginActionSpec(name="delete_draft", label="删除草稿", description="删除指定微信草稿。"),
        PluginActionSpec(name="publish_draft", label="发布草稿", description="把现有草稿送入发布流程。"),
        PluginActionSpec(name="list_materials", label="图库列表", description="分页获取微信永久图片素材。"),
        PluginActionSpec(name="upload_material_from_url", label="上传素材", description="从远程地址上传图片到微信图库。"),
        PluginActionSpec(name="delete_material", label="删除素材", description="删除微信永久图片素材。"),
        PluginActionSpec(name="preview_broadcast", label="预览发送", description="将图文预览发送到指定微信号或 OpenID。"),
        PluginActionSpec(name="send_broadcast", label="群发消息", description="按全部粉丝或标签发起真群发。"),
        PluginActionSpec(name="list_tasks", label="任务列表", description="获取本地记录的发布与群发任务。"),
        PluginActionSpec(name="refresh_task_status", label="刷新任务状态", description="刷新发布或群发任务状态。"),
        PluginActionSpec(name="query_publish_status", label="查询发布状态", description="根据 publish_id 查询发布状态。"),
        PluginActionSpec(name="create_qrcode", label="生成二维码", description="生成临时或永久二维码。"),
        PluginActionSpec(name="list_qrcodes", label="二维码记录", description="获取已生成二维码记录。"),
    ],
    get_settings=load_wechat_settings,
    save_settings=save_wechat_settings,
    call_action=wechat_call_action,
    icon="Promotion",
    author="Martin",
    publisher="natsume37",
    homepage="https://martin88.xyz",
    docs_url="https://github.com/natsume37/Blog-plugin-market/tree/main/plugins/wechat-official-account",
    repository_url="https://github.com/natsume37/Blog-backend",
    support_url="https://github.com/natsume37/Blog-backend/issues",
    issues_url="https://github.com/natsume37/Blog-backend/issues",
    license="MIT",
    verified=True,
    featured=True,
    install_strategy="builtin-toggle",
    runtime_type="builtin",
    min_app_version="1.0.0",
    features=["草稿管理", "微信图库", "预览发送", "真群发", "二维码", "状态反馈"],
    keywords=["wechat", "publishing", "distribution", "mass-send", "qrcode"],
    tags=["distribution", "social", "official"],
    capabilities=["wechat_draft", "wechat_material", "wechat_preview", "wechat_mass_send", "wechat_qrcode", "wechat_publish_status"],
    permissions=["network", "article_content", "plugin_settings", "plugin_storage"],
)
