import http.client
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.qiniu import normalize_remote_url


def test_normalize_remote_url_encodes_non_ascii_query_and_fragment() -> None:
    url = "https://cdn.example.com/封面 图.jpg?attname=封面图.jpg&download=你好 世界#片段 标题"

    normalized = normalize_remote_url(url)

    assert normalized == (
        "https://cdn.example.com/%E5%B0%81%E9%9D%A2%20%E5%9B%BE.jpg"
        "?attname=%E5%B0%81%E9%9D%A2%E5%9B%BE.jpg&download=%E4%BD%A0%E5%A5%BD%20%E4%B8%96%E7%95%8C"
        "#%E7%89%87%E6%AE%B5%20%E6%A0%87%E9%A2%98"
    )


def test_normalized_url_selector_is_ascii_safe_for_http_client() -> None:
    url = "https://cdn.example.com/image.jpg?attname=封面图.jpg"
    normalized = normalize_remote_url(url)
    parsed = urlsplit(normalized)
    selector = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    connection = http.client.HTTPConnection(parsed.netloc)

    connection.putrequest("GET", selector)
