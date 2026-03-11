import sys
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.plugins.builtin.wechat_official import _friendly_wechat_error


def _build_http_error(url: str, code: int) -> HTTPError:
    return HTTPError(url, code, "forbidden", hdrs=None, fp=BytesIO(b""))


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
