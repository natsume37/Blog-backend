import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.plugins.builtin.wechat_official import render_wechat_article_html


def test_render_wechat_article_html_adds_inline_styles_and_summary() -> None:
    result = render_wechat_article_html(
        "## 小节标题\n\n这里有一段正文，包含 `inline code`。\n\n![封面](https://cdn.example.com/poster.png)",
        summary="这是一段导语摘要",
        include_summary=True,
    )

    assert 'data-blog-wechat-render="1"' in result["html"]
    assert "Summary" in result["html"]
    assert "这是一段导语摘要" in result["html"]
    assert 'style="' in result["html"]
    assert "https://cdn.example.com/poster.png" in result["html"]
    assert "inline code" in result["plain_text"]
    assert result["warnings"] == []


def test_render_wechat_article_html_downgrades_media_and_warns_for_tables() -> None:
    result = render_wechat_article_html(
        '<video src="https://cdn.example.com/demo.mp4"></video>\n\n| 列一 | 列二 |\n| --- | --- |\n| A | B |',
        summary="",
        include_summary=False,
    )

    assert "视频内容请查看原链接" in result["html"]
    assert "https://cdn.example.com/demo.mp4" in result["html"]
    assert any("视频" in item for item in result["warnings"])
    assert any("表格" in item for item in result["warnings"])


def test_render_wechat_article_html_strips_scripts_and_warns_for_local_images() -> None:
    result = render_wechat_article_html(
        '<script>alert("xss")</script><img src="/static/example.png" alt="test" />',
        summary="",
        include_summary=False,
    )

    assert "<script" not in result["html"].lower()
    assert "/static/example.png" in result["html"]
    assert any("script/style/noscript" in item for item in result["warnings"])
    assert any("相对路径或本地图片" in item for item in result["warnings"])
