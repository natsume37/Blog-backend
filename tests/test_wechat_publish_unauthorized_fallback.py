import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.plugins.builtin import wechat_official


class _DummyArticle:
    def __init__(self) -> None:
        self.id = 19
        self.title = "demo"
        self.summary = "summary"
        self.content = "content"
        self.cover = "https://cdn.example.com/image.jpg"
        self.author_id = 1


def test_publish_mode_falls_back_to_draft_when_submit_is_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        wechat_official,
        "load_wechat_settings",
        lambda _db, _settings: {
            "app_id": "appid",
            "app_secret": "appsecret",
            "author": "Martin",
            "publish_mode": "publish",
            "content_source_url_base": "",
            "fallback_thumb_media_id": "fallback-media",
            "need_open_comment": True,
            "only_fans_can_comment": False,
            "preview_target_type": "towxname",
            "preview_target_value": "",
            "send_ignore_reprint": False,
            "default_tag_id": "",
        },
    )
    monkeypatch.setattr(wechat_official, "_exchange_access_token", lambda _appid, _secret: "token")
    monkeypatch.setattr(wechat_official, "_load_article_for_publish", lambda _db, _article_id: _DummyArticle())
    monkeypatch.setattr(
        wechat_official,
        "_build_wechat_article_payload",
        lambda _article, _db, _config, _token: {"title": "demo", "thumb_media_id": "fallback-media"},
    )
    monkeypatch.setattr(wechat_official, "_create_draft", lambda _token, _payload: {"media_id": "draft-media"})

    def _raise_unauthorized(_token: str, _media_id: str) -> dict:
        raise RuntimeError("WeChat API error 48001: api unauthorized rid: test-rid")

    monkeypatch.setattr(wechat_official, "_submit_publish", _raise_unauthorized)
    monkeypatch.setattr(wechat_official, "_create_task", lambda *args, **kwargs: {"id": 1, **kwargs})
    monkeypatch.setattr(wechat_official, "_serialize_task", lambda task: task)

    result = wechat_official.wechat_call_action("publish_article", {"article_id": 19, "publish_mode": "publish"}, db=None, settings=None)

    assert result["ok"] is True
    assert result["mode"] == "draft"
    assert result["media_id"] == "draft-media"
    assert "未授权发布接口" in result["message"]
    assert "48001" in result["warning"]
