import sys
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.article import Article
from app.services.plugins.builtin import wechat_official


def _build_article() -> Article:
    return Article(
        id=1,
        title="Cover fallback test",
        summary="summary",
        content="body",
        cover="https://cdn.example.com/image.jpg",
        author_id=1,
    )


def test_cover_upload_failure_falls_back_to_configured_media_id(monkeypatch: pytest.MonkeyPatch) -> None:
    article = _build_article()

    monkeypatch.setattr(wechat_official, "_rewrite_content_images", lambda _token, html: html)

    def _raise_http_error(_token: str, _url: str, timeout: int = 30) -> str:
        raise HTTPError("https://cdn.example.com/image.jpg", 403, "forbidden", hdrs=None, fp=BytesIO(b""))

    monkeypatch.setattr(wechat_official, "_upload_cover_as_material", _raise_http_error)

    payload = wechat_official._build_wechat_article_payload(
        article=article,
        db=None,  # type: ignore[arg-type]
        config={
            "author": "Martin",
            "content_source_url_base": "",
            "fallback_thumb_media_id": "fallback-media-id",
            "need_open_comment": True,
            "only_fans_can_comment": False,
        },
        access_token="access-token",
    )

    assert payload["thumb_media_id"] == "fallback-media-id"


def test_cover_upload_failure_without_fallback_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    article = _build_article()

    monkeypatch.setattr(wechat_official, "_rewrite_content_images", lambda _token, html: html)

    def _raise_http_error(_token: str, _url: str, timeout: int = 30) -> str:
        raise HTTPError("https://cdn.example.com/image.jpg", 403, "forbidden", hdrs=None, fp=BytesIO(b""))

    monkeypatch.setattr(wechat_official, "_upload_cover_as_material", _raise_http_error)

    with pytest.raises(RuntimeError) as exc_info:
        wechat_official._build_wechat_article_payload(
            article=article,
            db=None,  # type: ignore[arg-type]
            config={
                "author": "Martin",
                "content_source_url_base": "",
                "fallback_thumb_media_id": "",
                "need_open_comment": True,
                "only_fans_can_comment": False,
            },
            access_token="access-token",
        )

    assert "fallback_thumb_media_id" in str(exc_info.value)
