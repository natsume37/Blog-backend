import sys
from io import BytesIO
from pathlib import Path
from typing import Mapping
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.plugins.builtin.wechat_official import _friendly_wechat_error


def _build_http_error(url: str, code: int, headers: Mapping[str, str] | None = None) -> HTTPError:
    return HTTPError(url, code, "forbidden", hdrs=headers, fp=BytesIO(b""))


def test_friendly_wechat_error_for_wechat_api_403() -> None:
    error = _build_http_error("https://api.weixin.qq.com/cgi-bin/token", 403)

    message = _friendly_wechat_error(error)

    assert "HTTP 403" in message
    assert "IP 白名单" in message
    assert "AppID/AppSecret" in message


def test_friendly_wechat_error_for_asset_source_403() -> None:
    error = _build_http_error("https://cdn.example.com/covers/poster.jpg", 403)

    message = _friendly_wechat_error(error)

    assert "HTTP 403" in message
    assert "cdn.example.com" in message
    assert "公网匿名读取" in message


def test_friendly_wechat_error_includes_upstream_detail_for_asset_403() -> None:
    error = _build_http_error(
        "https://cdn.example.com/covers/poster.jpg",
        403,
        headers={"X-Error-Detail": "RHIE"},
    )

    message = _friendly_wechat_error(error)

    assert "上游详情：RHIE" in message
    assert "防盗链" in message


def test_friendly_wechat_error_for_wechat_api_48001() -> None:
    error = RuntimeError("WeChat API error 48001: api unauthorized rid: 69b12639-23d157f7-761e900f")

    message = _friendly_wechat_error(error)

    assert "errcode 48001" in message
    assert "接口未授权" in message
    assert "rid: 69b12639-23d157f7-761e900f" in message
