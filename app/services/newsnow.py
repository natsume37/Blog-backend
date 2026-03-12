import json
import logging
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from app.core.cache import redis_client
from app.schemas.news import NewsNowItem, NewsNowSourceGroup


logger = logging.getLogger(__name__)

NEWSNOW_ENTRY_URL = "https://newsnow.busiyi.world/c/realtime"
NEWSNOW_API_URL = "https://newsnow.busiyi.world/api/s/entire"
NEWSNOW_CACHE_KEY = "newsnow:realtime:feed:v1"
NEWSNOW_CACHE_TTL_SECONDS = 180

NEWSNOW_SOURCE_META: tuple[dict[str, str], ...] = (
    {
        "id": "zaobao",
        "name": "联合早报",
        "url": "https://www.zaobao.com",
        "description": "国际与中文实时新闻",
    },
    {
        "id": "wallstreetcn-quick",
        "name": "华尔街见闻",
        "url": "https://wallstreetcn.com",
        "description": "市场热点与商业快讯",
    },
    {
        "id": "cls-telegraph",
        "name": "财联社电报",
        "url": "https://www.cls.cn/telegraph",
        "description": "宏观、市场与公司快讯",
    },
    {
        "id": "36kr-quick",
        "name": "36氪快讯",
        "url": "https://www.36kr.com/newsflashes",
        "description": "创投与科技公司动态",
    },
    {
        "id": "ithome",
        "name": "IT之家",
        "url": "https://www.ithome.com",
        "description": "数码、软件与科技新闻",
    },
    {
        "id": "gelonghui",
        "name": "格隆汇",
        "url": "https://www.gelonghui.com",
        "description": "港美股与产业资讯",
    },
    {
        "id": "jin10",
        "name": "金十数据",
        "url": "https://www.jin10.com",
        "description": "交易与宏观即时播报",
    },
    {
        "id": "fastbull-express",
        "name": "FastBull 快讯",
        "url": "https://www.fastbull.com",
        "description": "全球财经与汇市消息",
    },
    {
        "id": "pcbeta-windows11",
        "name": "PCBeta",
        "url": "https://bbs.pcbeta.com",
        "description": "Windows 与系统社区动态",
    },
)


def _request_newsnow_payload() -> list[dict[str, Any]]:
    payload = json.dumps({"sources": [item["id"] for item in NEWSNOW_SOURCE_META]}).encode("utf-8")
    request = UrlRequest(
        NEWSNOW_API_URL,
        data=payload,
        method="POST",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://newsnow.busiyi.world",
            "Referer": NEWSNOW_ENTRY_URL,
        },
    )
    with urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", errors="ignore")
    data = json.loads(body)
    if not isinstance(data, list):
        raise ValueError("NewsNow payload is not a list")
    return data


def _coerce_timestamp(raw_item: dict[str, Any]) -> int | None:
    candidates = [
        raw_item.get("pubDate"),
        raw_item.get("date"),
    ]
    extra = raw_item.get("extra")
    if isinstance(extra, dict):
        candidates.append(extra.get("date"))

    for candidate in candidates:
        if isinstance(candidate, (int, float)) and int(candidate) > 0:
            return int(candidate)
        if isinstance(candidate, str) and candidate.strip().isdigit():
            return int(candidate.strip())
    return None


def _normalize_newsnow_groups(payload: list[dict[str, Any]], *, limit_per_source: int) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []

    for source in NEWSNOW_SOURCE_META:
        source_id = source["id"]
        raw_group = next(
            (
                item
                for item in payload
                if str(item.get("id") or "").strip() == source_id
            ),
            None,
        )
        if not isinstance(raw_group, dict):
            continue

        raw_items = raw_group.get("items")
        if not isinstance(raw_items, list):
            continue

        items: list[dict[str, Any]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            title = str(raw_item.get("title") or "").strip()
            url = str(raw_item.get("url") or raw_item.get("mobileUrl") or "").strip()
            item_id = str(raw_item.get("id") or url).strip()
            if not title or not url or not item_id:
                continue
            items.append(
                NewsNowItem(
                    id=item_id,
                    title=title,
                    url=url,
                    publishedAt=_coerce_timestamp(raw_item),
                ).model_dump()
            )
            if len(items) >= limit_per_source:
                break

        if not items:
            continue

        normalized.append(
            NewsNowSourceGroup(
                sourceId=source_id,
                sourceName=source["name"],
                sourceUrl=source["url"],
                description=source["description"],
                status=str(raw_group.get("status") or "live").strip() or "live",
                items=items,
            ).model_dump()
        )

    return normalized


def get_newsnow_realtime_feed(*, limit_per_source: int = 12, force_refresh: bool = False) -> list[dict[str, Any]]:
    limit_per_source = max(1, min(limit_per_source, 30))
    cache_key = f"{NEWSNOW_CACHE_KEY}:{limit_per_source}"

    if not force_refresh:
        cached = redis_client.get(cache_key)
        if isinstance(cached, list) and cached:
            return cached

    try:
        payload = _request_newsnow_payload()
        normalized = _normalize_newsnow_groups(payload, limit_per_source=limit_per_source)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
        logger.warning("Fetch NewsNow realtime feed failed: %s", exc)
        if not force_refresh:
            cached = redis_client.get(cache_key)
            if isinstance(cached, list) and cached:
                return cached
        raise RuntimeError("新闻源暂时不可用，请稍后再试") from exc

    redis_client.set(cache_key, normalized, expire=NEWSNOW_CACHE_TTL_SECONDS)
    return normalized
