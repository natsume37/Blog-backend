from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import logging
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.core.cache import redis_client
from app.core.config import Settings, settings
from app.models.record import BookNoteCache, BookNoteSummary, BookRecord, BookSearchCache, WeReadSyncState

logger = logging.getLogger(__name__)


class WeReadNotConfigured(RuntimeError):
    pass


class WeReadGatewayError(RuntimeError):
    pass


@dataclass
class WeReadSyncSummary:
    status: str
    message: str
    books_synced: int = 0
    notes_synced: int = 0
    skipped: bool = False


def _build_gateway_body(api_name: str, skill_version: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {"api_name": api_name, "skill_version": skill_version}
    if params:
        body.update(params)
    return body


def _seconds_to_duration(seconds: int | None) -> str:
    seconds = max(0, int(seconds or 0))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours <= 0:
        return f"{minutes}分钟"
    if minutes <= 0:
        return f"{hours}小时"
    return f"{hours}小时{minutes}分钟"


def _calculate_note_count(item: dict[str, Any] | None) -> int:
    if not item:
        return 0
    return int(item.get("reviewCount") or 0) + int(item.get("noteCount") or 0) + int(item.get("bookmarkCount") or 0)


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        timestamp = int(value or 0)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp)


def _truncate_text(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _json_list(values: list[str]) -> str:
    return json.dumps([item for item in values if item], ensure_ascii=False)


def _loads_json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
        if isinstance(value, list):
            return [str(item) for item in value if str(item)]
    except Exception:
        pass
    return []


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _rating_to_five(value: Any) -> float:
    score = _safe_float(value)
    if score <= 0:
        return 0
    return round(min(score, 100) / 20, 1)


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    try:
        return bool(int(value or 0))
    except (TypeError, ValueError):
        return bool(value)


def _stable_cover_colors(seed: str) -> tuple[str, str]:
    palettes = [
        ("#c66b3d", "#224c4a"),
        ("#2f6c8f", "#d79a43"),
        ("#4b6f44", "#18231f"),
        ("#6a5a8a", "#111827"),
        ("#7b3449", "#152029"),
        ("#8f2d2d", "#1e1613"),
    ]
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return palettes[int(digest[:2], 16) % len(palettes)]


def _reading_link(book_id: str, chapter_uid: str | None = None) -> str:
    if not book_id:
        return ""
    if chapter_uid:
        return f"weread://reading?bId={book_id}&chapterUid={chapter_uid}"
    return f"weread://reading?bId={book_id}"


def _bookmark_link(book_id: str, chapter_uid: str | None, raw_range: str | None, user_vid: str | None = None) -> str:
    if not (book_id and chapter_uid and raw_range and "-" in raw_range):
        return ""
    start, end = raw_range.split("-", 1)
    link = f"weread://bestbookmark?bookId={book_id}&chapterUid={chapter_uid}&rangeStart={start}&rangeEnd={end}"
    if user_vid:
        link = f"{link}&userVid={user_vid}"
    return link


def _status_from_progress(progress: int, finish_reading: bool, last_read_at: datetime | None) -> str:
    if finish_reading or progress >= 100:
        return "已读完"
    if progress > 0 or last_read_at:
        return "阅读中"
    return "待读"


class WeReadGatewayClient:
    def __init__(self, cfg: Settings = settings):
        self.cfg = cfg
        self.api_key = (cfg.WEREAD_API_KEY or "").strip()
        if not self.api_key:
            raise WeReadNotConfigured("WEREAD_API_KEY 未配置")

    def call(self, api_name: str, **params: Any) -> dict[str, Any]:
        body = _build_gateway_body(api_name, self.cfg.WEREAD_SKILL_VERSION, params)
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = Request(
            self.cfg.WEREAD_GATEWAY_URL,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "BlogBackend/WeReadSync",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            raise WeReadGatewayError(f"微信读书接口调用失败: {exc}") from exc

        if isinstance(data, dict) and data.get("upgrade_info"):
            message = data.get("upgrade_info", {}).get("message") or "微信读书 Skill 需要升级"
            raise WeReadGatewayError(str(message))

        errcode = data.get("errcode", data.get("errCode", 0)) if isinstance(data, dict) else 0
        if errcode not in (0, None):
            errmsg = data.get("errmsg") or data.get("errMsg") or data.get("message") or "微信读书接口返回错误"
            raise WeReadGatewayError(f"{errmsg} ({errcode})")

        if not isinstance(data, dict):
            raise WeReadGatewayError("微信读书接口返回格式异常")
        return data


def _fetch_all_notebooks(client: WeReadGatewayClient, count: int = 100) -> list[dict[str, Any]]:
    books: list[dict[str, Any]] = []
    last_sort: int | None = None
    seen_sorts: set[int] = set()
    for _ in range(100):
        params: dict[str, Any] = {"count": count}
        if last_sort:
            params["lastSort"] = last_sort
        data = client.call("/user/notebooks", **params)
        page_books = data.get("books") or []
        if not isinstance(page_books, list):
            break
        books.extend(page_books)
        if not data.get("hasMore") or not page_books:
            break
        next_sort = int(page_books[-1].get("sort") or 0)
        if next_sort <= 0 or next_sort in seen_sorts:
            break
        seen_sorts.add(next_sort)
        last_sort = next_sort
    return books


def _extract_book_id(item: dict[str, Any]) -> str:
    return str(item.get("bookId") or item.get("book", {}).get("bookId") or "").strip()


def _fetch_note_summaries(client: WeReadGatewayClient, book_id: str, limit: int = 3) -> tuple[list[dict[str, Any]], int]:
    summaries: list[dict[str, Any]] = []
    rating = 0

    try:
        bookmark_data = client.call("/book/bookmarklist", bookId=book_id)
        chapters = {
            str(item.get("chapterUid")): str(item.get("title") or "")
            for item in (bookmark_data.get("chapters") or [])
            if isinstance(item, dict)
        }
        for item in bookmark_data.get("updated") or []:
            if len(summaries) >= limit:
                break
            text = _truncate_text(item.get("markText"))
            if not text:
                continue
            chapter_uid = str(item.get("chapterUid") or "")
            summaries.append({
                "source_id": str(item.get("bookmarkId") or f"bookmark:{chapter_uid}:{item.get('range') or len(summaries)}"),
                "note_type": "highlight",
                "chapter_title": chapters.get(chapter_uid, ""),
                "content_summary": text,
                "source_created_at": _parse_timestamp(item.get("createTime")),
            })
    except WeReadGatewayError as exc:
        logger.info("Skip bookmark summaries for %s: %s", book_id, exc)

    try:
        review_data = client.call("/review/list/mine", bookid=book_id, count=20)
        for item in review_data.get("reviews") or []:
            if len(summaries) >= limit:
                break
            review = item.get("review") if isinstance(item, dict) else None
            if not isinstance(review, dict):
                continue
            text = _truncate_text(review.get("content"))
            if not text:
                continue
            star = int(review.get("star") or 0)
            if star > rating:
                rating = star
            summaries.append({
                "source_id": str(review.get("reviewId") or f"review:{review.get('createTime') or len(summaries)}"),
                "note_type": "review",
                "chapter_title": str(review.get("chapterName") or ""),
                "content_summary": text,
                "source_created_at": _parse_timestamp(review.get("createTime")),
            })
    except WeReadGatewayError as exc:
        logger.info("Skip review summaries for %s: %s", book_id, exc)

    return summaries, rating


def _normalize_search_book(item: dict[str, Any], keyword: str = "", from_cache: bool = False) -> dict[str, Any]:
    book = item.get("bookInfo") if isinstance(item.get("bookInfo"), dict) else item
    rating_raw = item.get("newRating", book.get("newRating"))
    rating_count = item.get("newRatingCount", book.get("newRatingCount"))
    rating_detail = item.get("newRatingDetail", book.get("newRatingDetail")) or {}
    if isinstance(rating_detail, dict) and not rating_count:
        rating_count = rating_detail.get("count")
    return {
        "source_id": str(book.get("bookId") or item.get("bookId") or "").strip(),
        "title": str(book.get("title") or item.get("title") or "未命名书籍"),
        "author": str(book.get("author") or item.get("author") or ""),
        "translator": str(book.get("translator") or ""),
        "cover": str(book.get("cover") or item.get("cover") or ""),
        "intro": str(book.get("intro") or item.get("intro") or ""),
        "category": str(book.get("category") or item.get("category") or ""),
        "publisher": str(book.get("publisher") or ""),
        "publish_time": str(book.get("publishTime") or book.get("publish_time") or ""),
        "isbn": str(book.get("isbn") or ""),
        "word_count": _safe_int(book.get("wordCount")),
        "rating": _rating_to_five(rating_raw),
        "rating_count": _safe_int(rating_count),
        "reading_count": _safe_int(item.get("readingCount", book.get("readingCount"))),
        "price": _safe_int(book.get("price")),
        "pay_type": _safe_int(book.get("payType")),
        "soldout": _parse_bool(book.get("soldout")),
        "source": "weread",
        "from_cache": from_cache,
        "_keyword": keyword,
        "_rating_raw": _safe_int(rating_raw),
        "_raw": item,
    }


def _search_cache_to_dict(cache: BookSearchCache) -> dict[str, Any]:
    return {
        "source_id": cache.source_id,
        "title": cache.title,
        "author": cache.author or "",
        "translator": cache.translator or "",
        "cover": cache.cover or "",
        "intro": cache.intro or "",
        "category": cache.category or "",
        "publisher": cache.publisher or "",
        "publish_time": cache.publish_time or "",
        "isbn": cache.isbn or "",
        "word_count": cache.word_count or 0,
        "rating": _rating_to_five(cache.rating),
        "rating_count": cache.rating_count or 0,
        "reading_count": cache.reading_count or 0,
        "price": cache.price or 0,
        "pay_type": cache.pay_type or 0,
        "soldout": bool(cache.soldout),
        "source": cache.source or "weread",
        "from_cache": True,
    }


def _cache_search_book(db: Session, item: dict[str, Any]) -> None:
    source_id = item.get("source_id")
    if not source_id:
        return
    cache = db.query(BookSearchCache).filter(BookSearchCache.source_id == source_id).first()
    if not cache:
        cache = BookSearchCache(source_id=source_id)
        db.add(cache)
    cache.source = "weread"
    cache.title = item.get("title") or "未命名书籍"
    cache.author = item.get("author") or ""
    cache.translator = item.get("translator") or ""
    cache.cover = item.get("cover") or ""
    cache.intro = item.get("intro") or ""
    cache.category = item.get("category") or ""
    cache.publisher = item.get("publisher") or ""
    cache.publish_time = item.get("publish_time") or ""
    cache.isbn = item.get("isbn") or ""
    cache.word_count = _safe_int(item.get("word_count"))
    cache.rating = _safe_int(item.get("_rating_raw")) or round(_safe_float(item.get("rating")) * 20)
    cache.rating_count = _safe_int(item.get("rating_count"))
    cache.reading_count = _safe_int(item.get("reading_count"))
    cache.price = _safe_int(item.get("price"))
    cache.pay_type = _safe_int(item.get("pay_type"))
    cache.soldout = bool(item.get("soldout"))
    cache.search_keyword = item.get("_keyword") or cache.search_keyword or ""
    cache.raw_json = json.dumps(item.get("_raw") or {}, ensure_ascii=False)


def _local_search_fallback(db: Session, keyword: str, limit: int) -> list[dict[str, Any]]:
    kw = keyword.strip()
    if not kw:
        return []
    cache_query = db.query(BookSearchCache).filter(
        (BookSearchCache.title.contains(kw))
        | (BookSearchCache.author.contains(kw))
        | (BookSearchCache.category.contains(kw))
        | (BookSearchCache.intro.contains(kw))
        | (BookSearchCache.search_keyword.contains(kw))
    )
    cached = [_search_cache_to_dict(item) for item in cache_query.order_by(BookSearchCache.updated_at.desc()).limit(limit).all()]
    seen = {item["source_id"] for item in cached}

    record_query = db.query(BookRecord).filter(
        BookRecord.source == "weread",
        BookRecord.is_in_shelf == True,
        (BookRecord.title.contains(kw))
        | (BookRecord.author.contains(kw))
        | (BookRecord.category.contains(kw))
        | (BookRecord.note_summary.contains(kw))
        | (BookRecord.tags_json.contains(kw)),
    )
    for record in record_query.order_by(BookRecord.last_read_at.desc(), BookRecord.updated_at.desc()).limit(limit).all():
        if record.source_id in seen:
            continue
        cached.append({
            "source_id": record.source_id,
            "title": record.title,
            "author": record.author or "",
            "cover": record.cover or "",
            "intro": record.intro or record.note_summary or "",
            "category": record.category or "",
            "publisher": record.publisher or "",
            "publish_time": record.publish_time or "",
            "isbn": record.isbn or "",
            "word_count": record.word_count or 0,
            "rating": _rating_to_five(record.weread_rating or record.rating * 10),
            "rating_count": record.weread_rating_count or 0,
            "reading_count": 0,
            "price": 0,
            "pay_type": 0,
            "soldout": False,
            "source": "weread",
            "from_cache": True,
        })
        seen.add(record.source_id)
        if len(cached) >= limit:
            break
    return cached[:limit]


def search_weread_books(
    db: Session,
    cfg: Settings,
    keyword: str,
    scope: int = 10,
    count: int = 12,
    max_idx: int = 0,
) -> tuple[list[dict[str, Any]], str]:
    keyword = keyword.strip()
    if not keyword:
        return [], "请输入搜索关键词"
    try:
        client = WeReadGatewayClient(cfg)
        data = client.call("/store/search", keyword=keyword, scope=scope, count=count, maxIdx=max_idx)
        results = data.get("results") if isinstance(data.get("results"), list) else []
        books: list[dict[str, Any]] = []
        for group in results:
            if not isinstance(group, dict):
                continue
            for item in group.get("books") or []:
                if not isinstance(item, dict):
                    continue
                normalized = _normalize_search_book(item, keyword=keyword)
                if normalized["source_id"]:
                    _cache_search_book(db, normalized)
                    books.append(normalized)
        db.commit()
        return books[:count], "success"
    except Exception as exc:
        db.rollback()
        logger.info("WeRead search fallback for %s: %s", keyword, exc)
        cached = _local_search_fallback(db, keyword, count)
        message = "微信读书搜索暂不可用，已展示本地缓存" if cached else f"微信读书搜索暂不可用: {exc}"
        return cached, message


def _record_detail_fields(record: BookRecord | None) -> dict[str, Any]:
    if not record:
        return {}
    return {
        "local_record_id": record.id,
        "visibility": record.visibility or "private",
        "progress": record.progress or 0,
        "read_seconds": record.read_seconds or 0,
        "read_duration": _seconds_to_duration(record.read_seconds),
        "status": record.status or "待读",
        "note_count": record.note_count or 0,
        "highlight_count": record.highlight_count or 0,
        "review_count": record.review_count or 0,
        "bookmark_count": record.bookmark_count or 0,
        "tags": _loads_json_list(record.tags_json),
        "last_read_at": record.last_read_at,
        "finished_at": record.finished_at,
        "detail_synced_at": record.detail_synced_at,
    }


def _chapter_to_dict(book_id: str, item: dict[str, Any]) -> dict[str, Any]:
    chapter_uid = str(item.get("chapterUid") or "")
    return {
        "chapter_uid": chapter_uid,
        "chapter_idx": _safe_int(item.get("chapterIdx")),
        "title": str(item.get("title") or ""),
        "level": _safe_int(item.get("level")) or 1,
        "word_count": _safe_int(item.get("wordCount")),
        "update_time": _parse_timestamp(item.get("updateTime")),
        "price": _safe_int(item.get("price")),
        "paid": _parse_bool(item.get("paid")),
        "deep_link": _reading_link(book_id, chapter_uid),
    }


def get_weread_book_detail(db: Session, cfg: Settings, book_id: str) -> tuple[dict[str, Any], str]:
    book_id = book_id.strip()
    record = db.query(BookRecord).filter(BookRecord.source == "weread", BookRecord.source_id == book_id).first()
    cache = db.query(BookSearchCache).filter(BookSearchCache.source_id == book_id).first()
    base = _search_cache_to_dict(cache) if cache else {
        "source_id": book_id,
        "title": record.title if record else "未命名书籍",
        "author": record.author if record else "",
        "cover": record.cover if record else "",
        "intro": record.intro if record else "",
        "category": record.category if record else "",
        "publisher": record.publisher if record else "",
        "publish_time": record.publish_time if record else "",
        "isbn": record.isbn if record else "",
        "word_count": record.word_count if record else 0,
        "rating": _rating_to_five(record.weread_rating if record else 0),
        "rating_count": record.weread_rating_count if record else 0,
        "reading_count": 0,
        "price": 0,
        "pay_type": 0,
        "soldout": False,
        "source": "weread",
        "from_cache": True,
    }
    base.update(_record_detail_fields(record))
    base.setdefault("chapters", [])

    try:
        client = WeReadGatewayClient(cfg)
        info = client.call("/book/info", bookId=book_id)
        info_book = info.get("bookInfo") if isinstance(info.get("bookInfo"), dict) else info
        normalized = _normalize_search_book(info_book, from_cache=False)
        normalized["source_id"] = normalized["source_id"] or book_id
        _cache_search_book(db, normalized)

        progress_book: dict[str, Any] = {}
        try:
            progress_book = client.call("/book/getprogress", bookId=book_id).get("book") or {}
        except WeReadGatewayError as exc:
            logger.info("Skip detail progress for %s: %s", book_id, exc)
        progress = max(0, min(100, _safe_int(progress_book.get("progress"))))
        last_read_at = _parse_timestamp(progress_book.get("updateTime"))
        finished_at = _parse_timestamp(progress_book.get("finishTime"))

        chapters: list[dict[str, Any]] = []
        try:
            chapter_data = client.call("/book/chapterinfo", bookId=book_id)
            chapters = [_chapter_to_dict(book_id, item) for item in chapter_data.get("chapters") or [] if isinstance(item, dict)]
        except WeReadGatewayError as exc:
            logger.info("Skip chapter detail for %s: %s", book_id, exc)

        if record:
            record.intro = normalized.get("intro") or record.intro
            record.publisher = normalized.get("publisher") or record.publisher
            record.publish_time = normalized.get("publish_time") or record.publish_time
            record.isbn = normalized.get("isbn") or record.isbn
            record.word_count = _safe_int(normalized.get("word_count")) or record.word_count
            record.weread_rating = _safe_int(normalized.get("_rating_raw")) or record.weread_rating
            record.weread_rating_count = _safe_int(normalized.get("rating_count")) or record.weread_rating_count
            record.chapter_count = len(chapters) or record.chapter_count
            record.detail_synced_at = datetime.now()
            if progress_book:
                record.progress = progress
                record.read_seconds = _safe_int(progress_book.get("recordReadingTime")) or record.read_seconds
                record.status = _status_from_progress(progress, bool(finished_at), last_read_at)
                record.last_read_at = last_read_at or record.last_read_at
                record.finished_at = finished_at or record.finished_at
        db.commit()

        detail = {**base, **normalized, **_record_detail_fields(record)}
        detail.update({
            "progress": progress if progress_book else detail.get("progress", 0),
            "read_seconds": _safe_int(progress_book.get("recordReadingTime")) or detail.get("read_seconds", 0),
            "read_duration": _seconds_to_duration(_safe_int(progress_book.get("recordReadingTime")) or detail.get("read_seconds", 0)),
            "status": _status_from_progress(progress, bool(finished_at), last_read_at) if progress_book else detail.get("status", "待读"),
            "last_read_at": last_read_at or detail.get("last_read_at"),
            "finished_at": finished_at or detail.get("finished_at"),
            "chapters": chapters,
            "from_cache": False,
        })
        return detail, "success"
    except Exception as exc:
        db.rollback()
        logger.info("WeRead detail fallback for %s: %s", book_id, exc)
        base["from_cache"] = True
        return base, "微信读书详情暂不可用，已展示本地缓存" if (record or cache) else f"微信读书详情暂不可用: {exc}"


def _note_cache_to_dict(item: BookNoteCache) -> dict[str, Any]:
    return {
        "source_id": item.source_id,
        "note_type": item.note_type,
        "chapter_uid": item.chapter_uid or "",
        "chapter_title": item.chapter_title or "",
        "content": item.content or "",
        "abstract": item.abstract or "",
        "location_range": item.location_range or "",
        "color_style": item.color_style or "",
        "deep_link": item.deep_link or "",
        "source_created_at": item.source_created_at,
    }


def _group_notes(book_id: str, title: str, items: list[dict[str, Any]], from_cache: bool) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in sorted(items, key=lambda value: value.get("source_created_at") or datetime.min, reverse=True):
        key = (item.get("chapter_uid") or "", item.get("chapter_title") or "未分章节")
        grouped.setdefault(key, []).append(item)
    chapters = [
        {"chapter_uid": key[0], "chapter_title": key[1], "items": value}
        for key, value in grouped.items()
    ]
    return {
        "source_id": book_id,
        "title": title,
        "total": len(items),
        "highlight_count": len([item for item in items if item.get("note_type") == "highlight"]),
        "review_count": len([item for item in items if item.get("note_type") == "review"]),
        "from_cache": from_cache,
        "chapters": chapters,
    }


def _cached_notes(db: Session, book_id: str) -> dict[str, Any]:
    record = db.query(BookRecord).filter(BookRecord.source == "weread", BookRecord.source_id == book_id).first()
    cache = db.query(BookSearchCache).filter(BookSearchCache.source_id == book_id).first()
    rows = db.query(BookNoteCache).filter(BookNoteCache.source_book_id == book_id).order_by(BookNoteCache.source_created_at.desc()).all()
    title = (record.title if record else "") or (cache.title if cache else "")
    return _group_notes(book_id, title, [_note_cache_to_dict(item) for item in rows], True)


def fetch_weread_book_notes(db: Session, cfg: Settings, book_id: str) -> tuple[dict[str, Any], str]:
    book_id = book_id.strip()
    record = db.query(BookRecord).filter(BookRecord.source == "weread", BookRecord.source_id == book_id).first()
    try:
        client = WeReadGatewayClient(cfg)
        bookmark_data = client.call("/book/bookmarklist", bookId=book_id)
        chapters = {
            str(item.get("chapterUid")): str(item.get("title") or "")
            for item in (bookmark_data.get("chapters") or [])
            if isinstance(item, dict)
        }
        notes: list[dict[str, Any]] = []
        for item in bookmark_data.get("updated") or []:
            if not isinstance(item, dict):
                continue
            content = _truncate_text(item.get("markText"), limit=2000)
            if not content:
                continue
            chapter_uid = str(item.get("chapterUid") or "")
            raw_range = str(item.get("range") or "")
            notes.append({
                "source_id": str(item.get("bookmarkId") or f"bookmark:{chapter_uid}:{raw_range}"),
                "note_type": "highlight",
                "chapter_uid": chapter_uid,
                "chapter_title": chapters.get(chapter_uid, ""),
                "content": content,
                "abstract": "",
                "location_range": raw_range,
                "color_style": str(item.get("colorStyle") or ""),
                "deep_link": _bookmark_link(book_id, chapter_uid, raw_range, str(item.get("userVid") or "")),
                "source_created_at": _parse_timestamp(item.get("createTime")),
            })

        synckey = 0
        for _ in range(5):
            review_data = client.call("/review/list/mine", bookid=book_id, count=50, synckey=synckey)
            for item in review_data.get("reviews") or []:
                review = item.get("review") if isinstance(item, dict) else None
                if not isinstance(review, dict):
                    continue
                content = _truncate_text(review.get("content"), limit=2000)
                if not content:
                    continue
                chapter_uid = str(review.get("chapterUid") or "")
                raw_range = str(review.get("range") or "")
                abstract = str(review.get("abstract") or "")
                notes.append({
                    "source_id": str(review.get("reviewId") or f"review:{review.get('createTime') or len(notes)}"),
                    "note_type": "review",
                    "chapter_uid": chapter_uid,
                    "chapter_title": str(review.get("chapterName") or chapters.get(chapter_uid, "")),
                    "content": content,
                    "abstract": abstract,
                    "location_range": raw_range,
                    "color_style": "",
                    "deep_link": _bookmark_link(book_id, chapter_uid, raw_range),
                    "source_created_at": _parse_timestamp(review.get("createTime")),
                })
            if not review_data.get("hasMore"):
                break
            next_synckey = _safe_int(review_data.get("synckey"))
            if next_synckey <= 0 or next_synckey == synckey:
                break
            synckey = next_synckey

        db.query(BookNoteCache).filter(BookNoteCache.source_book_id == book_id).delete(synchronize_session=False)
        now = datetime.now()
        for note in notes:
            db.add(BookNoteCache(
                book_record_id=record.id if record else None,
                source_book_id=book_id,
                source_id=note["source_id"],
                note_type=note["note_type"],
                chapter_uid=note["chapter_uid"],
                chapter_title=note["chapter_title"],
                content=note["content"],
                abstract=note["abstract"],
                location_range=note["location_range"],
                color_style=note["color_style"],
                deep_link=note["deep_link"],
                source_created_at=note["source_created_at"],
                synced_at=now,
            ))
        if record:
            record.highlight_count = len([item for item in notes if item["note_type"] == "highlight"])
            record.review_count = len([item for item in notes if item["note_type"] == "review"])
            record.note_count = record.highlight_count + record.review_count + (record.bookmark_count or 0)
            record.note_summary = "；".join(item["content"] for item in notes[:2])
        db.commit()
        title = record.title if record else str((bookmark_data.get("book") or {}).get("title") or "")
        return _group_notes(book_id, title, notes, False), "success"
    except Exception as exc:
        db.rollback()
        logger.info("WeRead notes fallback for %s: %s", book_id, exc)
        cached = _cached_notes(db, book_id)
        if cached["total"] > 0:
            return cached, "微信读书笔记暂不可用，已展示本地缓存"
        return cached, f"微信读书笔记暂不可用: {exc}"


def _get_sync_state(db: Session) -> WeReadSyncState:
    state = db.query(WeReadSyncState).filter(WeReadSyncState.key == "weread").first()
    if state:
        return state
    state = WeReadSyncState(key="weread")
    db.add(state)
    db.flush()
    return state


def _set_sync_state(
    db: Session,
    status: str,
    message: str = "",
    error: str = "",
    books_synced: int = 0,
    notes_synced: int = 0,
    stats: dict[str, Any] | None = None,
    success: bool = False,
) -> WeReadSyncState:
    now = datetime.now()
    state = _get_sync_state(db)
    state.status = status
    state.message = message
    state.last_error = error
    state.last_finished_at = now
    state.books_synced = books_synced
    state.notes_synced = notes_synced
    if stats is not None:
        state.stats_json = json.dumps(stats, ensure_ascii=False)
    if success:
        state.last_success_at = now
    return state


SYNC_LOCK_KEY = "weread:sync:lock"


def _acquire_sync_lock(cfg: Settings) -> str | None:
    token = uuid.uuid4().hex
    try:
        locked = redis_client.get_client().set(SYNC_LOCK_KEY, token, ex=cfg.WEREAD_SYNC_LOCK_SECONDS, nx=True)
        return token if locked else None
    except Exception as exc:
        logger.warning("Redis lock unavailable for WeRead sync: %s", exc)
        return None


def _release_sync_lock(token: str | None) -> None:
    if not token:
        return
    try:
        client = redis_client.get_client()
        if client.get(SYNC_LOCK_KEY) == token:
            client.delete(SYNC_LOCK_KEY)
    except Exception:
        pass


def sync_weread_records(db: Session, cfg: Settings = settings, force_notes: bool = False) -> WeReadSyncSummary:
    if not cfg.WEREAD_SYNC_ENABLED:
        _set_sync_state(db, "disabled", "微信读书同步未启用")
        db.commit()
        return WeReadSyncSummary(status="disabled", message="微信读书同步未启用", skipped=True)
    if not (cfg.WEREAD_API_KEY or "").strip():
        _set_sync_state(db, "not_configured", "WEREAD_API_KEY 未配置")
        db.commit()
        return WeReadSyncSummary(status="not_configured", message="WEREAD_API_KEY 未配置", skipped=True)
    lock_token = _acquire_sync_lock(cfg)
    if not lock_token:
        _set_sync_state(db, "skipped", "已有微信读书同步任务正在运行")
        db.commit()
        return WeReadSyncSummary(status="skipped", message="已有微信读书同步任务正在运行", skipped=True)

    state = _get_sync_state(db)
    state.status = "running"
    state.message = "微信读书同步中"
    state.last_error = ""
    state.last_started_at = datetime.now()
    db.commit()

    books_synced = 0
    notes_synced = 0
    try:
        client = WeReadGatewayClient(cfg)
        shelf = client.call("/shelf/sync")
        monthly_stats = client.call("/readdata/detail", mode="monthly")
        notebooks = _fetch_all_notebooks(client)
        notebook_by_book_id = {_extract_book_id(item): item for item in notebooks if _extract_book_id(item)}

        shelf_books = [item for item in shelf.get("books") or [] if isinstance(item, dict) and item.get("bookId")]
        db.query(BookRecord).filter(BookRecord.source == "weread").update({"is_in_shelf": False})

        for item in shelf_books:
            book_id = str(item.get("bookId"))
            notebook = notebook_by_book_id.get(book_id)
            progress_data: dict[str, Any] = {}
            try:
                progress_data = client.call("/book/getprogress", bookId=book_id).get("book") or {}
            except WeReadGatewayError as exc:
                logger.info("Skip progress for %s: %s", book_id, exc)

            last_read_at = _parse_timestamp(progress_data.get("updateTime") or item.get("readUpdateTime"))
            progress = int(progress_data.get("progress") or (notebook or {}).get("readingProgress") or 0)
            progress = max(0, min(progress, 100))
            finish_reading = bool(int(item.get("finishReading") or 0))
            note_count = _calculate_note_count(notebook)
            highlight_count = int((notebook or {}).get("noteCount") or 0)
            review_count = int((notebook or {}).get("reviewCount") or 0)
            bookmark_count = int((notebook or {}).get("bookmarkCount") or 0)

            is_secret = bool(int(item.get("secret") or 0))
            record = db.query(BookRecord).filter(BookRecord.source == "weread", BookRecord.source_id == book_id).first()
            old_note_count = record.note_count if record else -1
            if not record:
                color, accent = _stable_cover_colors(book_id)
                record = BookRecord(source="weread", source_id=book_id, color=color, accent=accent)
                record.visibility = "private"
                db.add(record)
            elif record.visibility not in {"public", "login", "private"}:
                record.visibility = "private"

            tags = [str(item.get("category") or "").strip(), "微信读书"]
            if note_count > 0:
                tags.append("有笔记")
            if is_secret:
                tags.append("私密阅读")

            record.title = str(item.get("title") or "未命名书籍")
            record.author = str(item.get("author") or "")
            record.cover = str(item.get("cover") or "")
            record.category = str(item.get("category") or "")
            record.format = "微信读书"
            record.status = _status_from_progress(progress, finish_reading, last_read_at)
            record.progress = progress
            record.read_seconds = int(progress_data.get("recordReadingTime") or 0)
            record.note_count = note_count
            record.highlight_count = highlight_count
            record.review_count = review_count
            record.bookmark_count = bookmark_count
            record.tags_json = _json_list(tags)
            record.is_private = is_secret
            record.is_top = bool(int(item.get("isTop") or 0))
            record.is_in_shelf = True
            record.last_read_at = last_read_at
            record.finished_at = _parse_timestamp(progress_data.get("finishTime"))
            record.synced_at = datetime.now()

            if note_count > 0 and (force_notes or note_count != old_note_count or not record.note_summary):
                summaries, rating = _fetch_note_summaries(client, book_id)
                if rating > 0:
                    record.rating = rating * 10
                record.notes.clear()
                for summary in summaries:
                    record.notes.append(BookNoteSummary(**summary))
                record.note_summary = "；".join(item["content_summary"] for item in summaries[:2])
                notes_synced += len(summaries)

            books_synced += 1

        _set_sync_state(
            db,
            "success",
            "微信读书同步完成",
            books_synced=books_synced,
            notes_synced=notes_synced,
            stats=monthly_stats,
            success=True,
        )
        db.commit()
        return WeReadSyncSummary(status="success", message="微信读书同步完成", books_synced=books_synced, notes_synced=notes_synced)
    except Exception as exc:
        db.rollback()
        _set_sync_state(db, "failed", "微信读书同步失败", error=str(exc), books_synced=books_synced, notes_synced=notes_synced)
        db.commit()
        logger.error("WeRead sync failed: %s", exc, exc_info=True)
        return WeReadSyncSummary(status="failed", message="微信读书同步失败", books_synced=books_synced, notes_synced=notes_synced)
    finally:
        _release_sync_lock(lock_token)


def book_record_to_dict(record: BookRecord, include_notes: bool = False) -> dict[str, Any]:
    rating = round((record.rating or 0) / 10, 1) if record.rating else 0
    data = {
        "id": record.id,
        "source_id": record.source_id,
        "title": record.title,
        "author": record.author or "",
        "cover": record.cover or "",
        "category": record.category or "",
        "publisher": record.publisher or "",
        "publish_time": record.publish_time or "",
        "isbn": record.isbn or "",
        "word_count": record.word_count or 0,
        "weread_rating": _rating_to_five(record.weread_rating),
        "weread_rating_count": record.weread_rating_count or 0,
        "chapter_count": record.chapter_count or 0,
        "format": record.format or "微信读书",
        "status": record.status,
        "progress": record.progress or 0,
        "rating": rating,
        "read_seconds": record.read_seconds or 0,
        "read_duration": _seconds_to_duration(record.read_seconds),
        "note_count": record.note_count or 0,
        "highlight_count": record.highlight_count or 0,
        "review_count": record.review_count or 0,
        "bookmark_count": record.bookmark_count or 0,
        "tags": _loads_json_list(record.tags_json),
        "note_summary": record.note_summary or "",
        "color": record.color or "#2f6c8f",
        "accent": record.accent or "#224c4a",
        "visibility": record.visibility or "private",
        "is_private": bool(record.is_private),
        "last_read_at": record.last_read_at,
        "finished_at": record.finished_at,
        "synced_at": record.synced_at,
        "detail_synced_at": record.detail_synced_at,
    }
    if include_notes:
        data["intro"] = record.intro or ""
        data["notes"] = [
            {
                "note_type": item.note_type,
                "chapter_title": item.chapter_title or "",
                "content_summary": item.content_summary or "",
                "source_created_at": item.source_created_at,
            }
            for item in sorted(record.notes, key=lambda item: item.source_created_at or datetime.min, reverse=True)
        ]
    return data


def build_local_book_recommendations(records: list[BookRecord], limit: int = 8) -> list[dict[str, Any]]:
    tag_frequency: dict[str, int] = {}
    category_frequency: dict[str, int] = {}
    for record in records:
        if record.category:
            category_frequency[record.category] = category_frequency.get(record.category, 0) + 1
        for tag in _loads_json_list(record.tags_json):
            if tag and tag != "微信读书":
                tag_frequency[tag] = tag_frequency.get(tag, 0) + 1

    scored: list[tuple[float, BookRecord, str]] = []
    for record in records:
        rating = _rating_to_five(record.weread_rating) or (round((record.rating or 0) / 10, 1) if record.rating else 0)
        tags = _loads_json_list(record.tags_json)
        score = rating * 18
        score += min(record.read_seconds or 0, 3600 * 30) / 3600
        score += min(record.note_count or 0, 60) * 0.35
        if 0 < (record.progress or 0) < 100:
            score += 12
        elif (record.progress or 0) >= 100:
            score += 8
        score += category_frequency.get(record.category or "", 0) * 1.6
        score += sum(tag_frequency.get(tag, 0) for tag in tags[:3]) * 0.8

        if 0 < (record.progress or 0) < 100:
            reason = f"正在阅读到 {record.progress}%，延续当前阅读节奏"
        elif rating >= 4.5:
            reason = f"{rating} 分高评分，适合作为重点回顾"
        elif record.note_count:
            reason = f"已有 {record.note_count} 条笔记，适合继续整理思考"
        elif record.category:
            reason = f"匹配你常读的「{record.category}」分类"
        else:
            reason = "基于本地书架和阅读进度推荐"
        scored.append((score, record, reason))

    scored.sort(key=lambda item: (item[0], item[1].last_read_at or item[1].updated_at or datetime.min), reverse=True)
    recommendations = []
    for _, record, reason in scored[:limit]:
        rating = _rating_to_five(record.weread_rating) or (round((record.rating or 0) / 10, 1) if record.rating else 0)
        recommendations.append({
            "source_id": record.source_id,
            "title": record.title,
            "author": record.author or "",
            "cover": record.cover or "",
            "category": record.category or "",
            "rating": rating,
            "rating_count": record.weread_rating_count or 0,
            "progress": record.progress or 0,
            "read_seconds": record.read_seconds or 0,
            "read_duration": _seconds_to_duration(record.read_seconds),
            "reason": reason,
            "tags": _loads_json_list(record.tags_json),
            "local_record_id": record.id,
        })
    return recommendations


def _load_sync_stats(state: WeReadSyncState | None) -> dict[str, Any]:
    if not state or not state.stats_json:
        return {}
    try:
        value = json.loads(state.stats_json)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def book_time_stats_to_dict(
    state: WeReadSyncState | None,
    records: list[BookRecord],
    include_breakdowns: bool = True,
) -> dict[str, Any]:
    stats = _load_sync_stats(state)
    record_read_seconds = sum(item.read_seconds or 0 for item in records)
    record_by_source_id = {item.source_id: item for item in records if item.source_id}

    daily = []
    read_times = stats.get("readTimes") if isinstance(stats.get("readTimes"), dict) else {}
    for raw_timestamp, raw_seconds in sorted(read_times.items(), key=lambda item: _safe_int(item[0])):
        timestamp = _safe_int(raw_timestamp)
        read_seconds = _safe_int(raw_seconds)
        if timestamp <= 0:
            continue
        date = datetime.fromtimestamp(timestamp)
        daily.append({
            "timestamp": timestamp,
            "date": date.strftime("%Y-%m-%d"),
            "label": date.strftime("%m.%d"),
            "read_seconds": read_seconds,
            "read_duration": _seconds_to_duration(read_seconds),
        })

    total_read_seconds = _safe_int(stats.get("totalReadTime")) or sum(item["read_seconds"] for item in daily) or record_read_seconds
    active_days = len([item for item in daily if item["read_seconds"] > 0])
    read_days = _safe_int(stats.get("readDays")) or active_days
    day_average_seconds = _safe_int(stats.get("dayAverageReadTime"))
    if day_average_seconds <= 0 and read_days > 0:
        day_average_seconds = total_read_seconds // read_days

    categories = []
    category_items = stats.get("preferCategory") if include_breakdowns and isinstance(stats.get("preferCategory"), list) else []
    for item in category_items[:8]:
        if not isinstance(item, dict):
            continue
        read_seconds = _safe_int(item.get("readingTime"))
        name = str(item.get("categoryTitle") or item.get("parentCategoryTitle") or "未分类")
        categories.append({
            "name": name,
            "parent_name": str(item.get("parentCategoryTitle") or ""),
            "reading_count": _safe_int(item.get("readingCount")),
            "read_seconds": read_seconds,
            "read_duration": _seconds_to_duration(read_seconds),
            "percent": round((read_seconds / total_read_seconds) * 100) if total_read_seconds else 0,
        })

    longest_books = []
    longest_items = stats.get("readLongest") if include_breakdowns and isinstance(stats.get("readLongest"), list) else []
    for item in longest_items[:8]:
        if not isinstance(item, dict):
            continue
        book = item.get("book") if isinstance(item.get("book"), dict) else {}
        source_id = str(book.get("bookId") or "")
        record = record_by_source_id.get(source_id)
        if not source_id or record is None:
            continue
        read_seconds = _safe_int(item.get("readTime"))
        longest_books.append({
            "source_id": source_id,
            "title": (record.title if record else str(book.get("title") or "未命名书籍")),
            "author": (record.author if record else str(book.get("author") or "")) or "",
            "cover": (record.cover if record else str(book.get("cover") or "")) or "",
            "read_seconds": read_seconds,
            "read_duration": _seconds_to_duration(read_seconds),
            "tags": _loads_json_list(record.tags_json) if record else [str(tag) for tag in item.get("tags", []) if tag],
        })

    return {
        "total_read_seconds": total_read_seconds,
        "total_read_duration": _seconds_to_duration(total_read_seconds),
        "day_average_seconds": day_average_seconds,
        "day_average_duration": _seconds_to_duration(day_average_seconds),
        "read_days": read_days,
        "active_days": active_days,
        "compare": _safe_float(stats.get("compare")),
        "book_count": len(records),
        "note_count": sum(item.note_count or 0 for item in records),
        "read_distribution_word": str(stats.get("readDistributionWord") or ""),
        "last_sync_at": state.last_success_at if state else None,
        "daily": daily,
        "categories": categories,
        "longest_books": longest_books,
    }


def sync_state_to_dict(state: WeReadSyncState | None, cfg: Settings = settings) -> dict[str, Any]:
    return {
        "configured": bool((cfg.WEREAD_API_KEY or "").strip()),
        "enabled": bool(cfg.WEREAD_SYNC_ENABLED),
        "status": state.status if state else "not_configured",
        "message": state.message if state else "",
        "last_error": state.last_error if state else "",
        "last_started_at": state.last_started_at if state else None,
        "last_finished_at": state.last_finished_at if state else None,
        "last_success_at": state.last_success_at if state else None,
        "books_synced": state.books_synced if state else 0,
        "notes_synced": state.notes_synced if state else 0,
    }


__all__ = [
    "WeReadGatewayClient",
    "WeReadGatewayError",
    "WeReadNotConfigured",
    "WeReadSyncSummary",
    "_build_gateway_body",
    "_calculate_note_count",
    "_fetch_all_notebooks",
    "_seconds_to_duration",
    "book_record_to_dict",
    "book_time_stats_to_dict",
    "build_local_book_recommendations",
    "fetch_weread_book_notes",
    "get_weread_book_detail",
    "search_weread_books",
    "sync_state_to_dict",
    "sync_weread_records",
]
