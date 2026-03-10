import logging
from dataclasses import dataclass
from typing import Iterable

from qiniu import Auth, BucketManager
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.resource import Resource


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResourceSyncStats:
    scanned: int
    created: int
    updated: int


def _build_bucket_manager(settings: Settings) -> BucketManager:
    if not settings.is_qiniu_enabled:
        raise ValueError("七牛云未配置，无法同步")
    auth = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
    return BucketManager(auth)


def _guess_media_type(key: str, mime_type: str | None) -> str:
    if mime_type:
        if mime_type.startswith("image/"):
            return "img"
        if mime_type.startswith("video/"):
            return "video"
        if mime_type.startswith("audio/"):
            return "audio"
    lower_key = (key or "").lower()
    if lower_key.startswith("img/"):
        return "img"
    if lower_key.startswith("video/"):
        return "video"
    if lower_key.startswith("audio/"):
        return "audio"
    return "other"


def delete_qiniu_resources(keys: Iterable[str], settings: Settings) -> int:
    normalized_keys = [str(key).strip() for key in keys if str(key).strip()]
    if not normalized_keys:
        return 0
    if not settings.is_qiniu_enabled:
        logger.info("Skipping Qiniu deletion for %d resources because configuration is missing", len(normalized_keys))
        return 0

    bucket = _build_bucket_manager(settings)
    failed = 0
    for key in normalized_keys:
        try:
            _ret, info = bucket.delete(settings.QINIU_BUCKET, key)
            if info.status_code not in (200, 612):
                failed += 1
                logger.warning("Failed to delete Qiniu object %s: status=%s", key, info.status_code)
        except Exception:
            failed += 1
            logger.exception("Qiniu delete error for key %s", key)
    return failed


def sync_qiniu_resources(
    db: Session,
    settings: Settings,
    *,
    prefix: str = "",
    limit: int = 1000,
    user_id: int | None = None,
) -> ResourceSyncStats:
    bucket = _build_bucket_manager(settings)

    normalized_limit = max(1, min(int(limit or 1000), 3000))
    normalized_prefix = (prefix or "").strip()
    marker = ""
    created = 0
    updated = 0
    scanned = 0
    domain = (settings.QINIU_DOMAIN or "").rstrip("/")

    while True:
        page_limit = min(1000, normalized_limit - scanned)
        ret, eof, info = bucket.list(
            settings.QINIU_BUCKET,
            prefix=normalized_prefix or None,
            marker=marker,
            limit=page_limit,
        )
        if info.status_code != 200:
            raise RuntimeError(f"同步失败，七牛返回状态码: {info.status_code}")

        items = ret.get("items", []) if ret else []
        marker = ret.get("marker", "") if ret else ""
        for item in items:
            key = item.get("key", "")
            if not key:
                continue
            scanned += 1
            if scanned > normalized_limit:
                break

            fsize = int(item.get("fsize", 0) or 0)
            mime_type = item.get("mimeType") or None
            media_type = _guess_media_type(key, mime_type)
            base_url = f"{domain}/{key}"

            existing = db.query(Resource).filter(Resource.key == key).first()
            if existing:
                changed = False
                if existing.size != fsize:
                    existing.size = fsize
                    changed = True
                if existing.mime_type != mime_type:
                    existing.mime_type = mime_type
                    changed = True
                if existing.url != base_url:
                    existing.url = base_url
                    changed = True
                if existing.media_type != media_type:
                    existing.media_type = media_type
                    changed = True
                if changed:
                    updated += 1
                continue

            db.add(
                Resource(
                    filename=key.split("/")[-1] or key,
                    key=key,
                    url=base_url,
                    media_type=media_type,
                    mime_type=mime_type,
                    size=fsize,
                    user_id=user_id,
                )
            )
            created += 1

        if scanned >= normalized_limit or eof or not marker:
            break

    return ResourceSyncStats(scanned=scanned, created=created, updated=updated)
