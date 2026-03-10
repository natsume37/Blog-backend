import html
import json
import mimetypes
import os
import re
import uuid
from typing import Any
from urllib import parse as urlparse
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.article import Article
from app.models.user import User
from app.utils.qiniu import normalize_remote_url
from app.services.plugins.base import (
    PluginActionSpec,
    PluginAdminPage,
    PluginSettingField,
    PluginSettingOption,
    PluginSpec,
)
from app.services.plugins.storage import get_plugin_settings_map, save_plugin_settings_map


WECHAT_PLUGIN_ID = "wechat-official-account"
_IMG_TAG_RE = re.compile(r'(<img\b[^>]*?\ssrc=")([^"]+)(")', re.IGNORECASE)


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


def _read_json_response(resp) -> dict[str, Any]:
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
        return _read_json_response(resp)


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


def _post_multipart(url: str, *, file_field: str, filename: str, file_bytes: bytes, content_type: str, timeout: int = 30) -> dict[str, Any]:
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
        return _read_json_response(resp)


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
    access_token = str(payload.get("access_token") or "").strip()
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
    media_id = str(payload.get("media_id") or "").strip()
    if not media_id:
        raise RuntimeError("上传封面到微信素材库失败，未返回 media_id")
    return media_id


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
    result_url = str(payload.get("url") or "").strip()
    if not result_url:
        raise RuntimeError("上传正文图片失败，未返回 url")
    return result_url


def _rewrite_content_images(access_token: str, html_content: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        original_url = (match.group(2) or "").strip()
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
        return (author.nickname or author.username or "").strip()
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
        "need_open_comment": _parse_bool(values.get("need_open_comment", "false"), False),
        "only_fans_can_comment": _parse_bool(values.get("only_fans_can_comment", "false"), False),
    }


def save_wechat_settings(db: Session, payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    current = load_wechat_settings(db, settings)
    merged = {
        "app_id": str(payload.get("app_id", current["app_id"])).strip(),
        "app_secret": str(payload.get("app_secret", current["app_secret"])).strip(),
        "author": str(payload.get("author", current["author"])).strip(),
        "publish_mode": str(payload.get("publish_mode", current["publish_mode"])).strip() or "draft",
        "content_source_url_base": str(payload.get("content_source_url_base", current["content_source_url_base"])).strip(),
        "fallback_thumb_media_id": str(payload.get("fallback_thumb_media_id", current["fallback_thumb_media_id"])).strip(),
        "need_open_comment": "true" if _parse_bool(payload.get("need_open_comment", current["need_open_comment"])) else "false",
        "only_fans_can_comment": "true" if _parse_bool(payload.get("only_fans_can_comment", current["only_fans_can_comment"])) else "false",
    }
    save_plugin_settings_map(db, WECHAT_PLUGIN_ID, merged)
    return load_wechat_settings(db, settings)


def _ensure_wechat_ready(config: dict[str, Any]) -> None:
    if not config["app_id"]:
        raise ValueError("请先配置 AppID")
    if not config["app_secret"]:
        raise ValueError("请先配置 AppSecret")


def _build_wechat_article_payload(article: Article, db: Session, config: dict[str, Any], access_token: str) -> dict[str, Any]:
    source_url = _absolute_article_url(config["content_source_url_base"], article)
    author_name = _resolve_author_name(article, db, config["author"])
    html_content = _render_article_html(article.content or "")
    html_content = _rewrite_content_images(access_token, html_content)

    thumb_media_id = config["fallback_thumb_media_id"].strip()
    if article.cover and _is_remote_url(article.cover):
        thumb_media_id = _upload_cover_as_material(access_token, article.cover)
    if not thumb_media_id:
        raise ValueError("文章没有可用封面，且插件未配置 fallback_thumb_media_id")

    digest = (article.summary or "").strip()
    return {
        "title": article.title or "",
        "author": author_name,
        "digest": digest,
        "content": html_content,
        "content_source_url": source_url,
        "thumb_media_id": thumb_media_id,
        "show_cover_pic": 1,
        "need_open_comment": 1 if _parse_bool(config["need_open_comment"], False) else 0,
        "only_fans_can_comment": 1 if _parse_bool(config["only_fans_can_comment"], False) else 0,
    }


def _create_draft(access_token: str, article_payload: dict[str, Any]) -> dict[str, Any]:
    return _request_json(
        f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={access_token}",
        data={"articles": [article_payload]},
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


def _friendly_wechat_error(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"微信公众号接口返回错误（HTTP {exc.code}）"
    if isinstance(exc, URLError):
        reason = str(getattr(exc, "reason", exc))
        return f"微信公众号接口网络异常：{reason}"
    text = str(exc).strip()
    return text or "微信公众号发布失败"


def wechat_call_action(action: str, payload: dict[str, Any], db: Session, settings: Settings) -> dict[str, Any]:
    config = load_wechat_settings(db, settings)
    if action == "test_connection":
        _ensure_wechat_ready(config)
        token = _exchange_access_token(config["app_id"], config["app_secret"])
        return {"ok": True, "message": "微信公众号连接成功", "access_token_preview": f"{token[:8]}..."}

    if action in {"publish_article", "publish"}:
        config = {
            **config,
            "author": str(payload.get("author", config["author"])).strip(),
            "publish_mode": str(payload.get("publish_mode", config["publish_mode"])).strip() or "draft",
            "need_open_comment": _parse_bool(payload.get("need_open_comment", config["need_open_comment"]), False),
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
        media_id = str(draft_result.get("media_id") or "").strip()
        if not media_id:
            raise RuntimeError("草稿创建成功但未返回 media_id")

        publish_mode = str(payload.get("publish_mode") or config["publish_mode"] or "draft").strip()
        result = {
            "ok": True,
            "message": "文章已同步到微信公众号草稿箱",
            "mode": "draft",
            "article_id": article.id,
            "title": article.title,
            "media_id": media_id,
        }
        if publish_mode == "publish":
            publish_result = _submit_publish(access_token, media_id)
            publish_id = str(publish_result.get("publish_id") or "").strip()
            result.update({
                "message": "文章已提交到微信公众号发布队列",
                "mode": "publish",
                "publish_id": publish_id,
                "publish_status": publish_result,
            })
        return result

    if action == "query_publish_status":
        _ensure_wechat_ready(config)
        publish_id = str(payload.get("publish_id") or "").strip()
        if not publish_id:
            raise ValueError("publish_id 不能为空")
        access_token = _exchange_access_token(config["app_id"], config["app_secret"])
        status = _query_publish_status(access_token, publish_id)
        return {"ok": True, "message": "获取发布状态成功", "status": status}

    raise KeyError(action)


WECHAT_PLUGIN = PluginSpec(
    plugin_id=WECHAT_PLUGIN_ID,
    name="微信公众号发布",
    version="1.0.0",
    description="把博客文章同步到微信公众号草稿箱，并可直接提交发布。",
    category="distribution",
    source="official",
    settings_schema=[
        PluginSettingField(key="app_id", label="AppID", type="text", required=True, placeholder="公众号 AppID"),
        PluginSettingField(key="app_secret", label="AppSecret", type="password", required=True, secret=True, placeholder="公众号 AppSecret"),
        PluginSettingField(key="default_author", label="默认作者", type="text", placeholder="可选，不填则使用文章作者"),
        PluginSettingField(key="site_base_url", label="站点地址", type="text", placeholder="例如 https://martin88.xyz"),
        PluginSettingField(
            key="publish_mode",
            label="默认同步模式",
            type="select",
            default="draft",
            options=[
                PluginSettingOption(label="仅保存为草稿", value="draft"),
                PluginSettingOption(label="创建草稿后直接提交发布", value="publish"),
            ],
        ),
        PluginSettingField(key="fallback_thumb_media_id", label="备用封面 Media ID", type="text", description="文章没有封面时使用。"),
        PluginSettingField(key="open_comment", label="开启评论", type="switch", default=False),
        PluginSettingField(key="only_fans_can_comment", label="仅粉丝可评论", type="switch", default=False),
    ],
    admin_pages=[
        PluginAdminPage(
            path="/admin/plugins/wechat-official-account/publisher",
            route_name="PluginWeChatOfficialAccount",
            title="微信公众号发布",
            menu_label="公众号发布",
            component_key="plugin.wechat.settings",
            icon="Promotion",
        ),
    ],
    actions=[
        PluginActionSpec(name="test_connection", label="测试连接", description="验证公众号凭证是否可用。"),
        PluginActionSpec(name="publish_article", label="发布文章", description="将文章上传到公众号草稿箱或发布队列。"),
        PluginActionSpec(name="query_publish_status", label="查询状态", description="根据 publish_id 查询发布状态。"),
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
    features=["草稿上传", "公众号发布", "封面同步", "发布状态查询"],
    keywords=["wechat", "publishing", "distribution", "cms"],
    tags=["distribution", "social", "official"],
    capabilities=["wechat_draft", "wechat_publish", "wechat_publish_status"],
    permissions=["network", "article_content", "plugin_settings"],
)
