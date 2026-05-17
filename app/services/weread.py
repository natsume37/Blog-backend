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
from app.models.record import BookNoteSummary, BookRecord, WeReadSyncState

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
                record.visibility = "private" if is_secret else "public"
                db.add(record)
            elif record.visibility not in {"public", "login", "private"}:
                record.visibility = "private" if is_secret else "public"

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
        "visibility": record.visibility or "public",
        "is_private": bool(record.is_private),
        "last_read_at": record.last_read_at,
        "finished_at": record.finished_at,
        "synced_at": record.synced_at,
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


def _load_sync_stats(state: WeReadSyncState | None) -> dict[str, Any]:
    if not state or not state.stats_json:
        return {}
    try:
        value = json.loads(state.stats_json)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def book_time_stats_to_dict(state: WeReadSyncState | None, records: list[BookRecord]) -> dict[str, Any]:
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
    category_items = stats.get("preferCategory") if isinstance(stats.get("preferCategory"), list) else []
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
    longest_items = stats.get("readLongest") if isinstance(stats.get("readLongest"), list) else []
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
    "sync_state_to_dict",
    "sync_weread_records",
]
