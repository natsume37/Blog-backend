import sys
import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base
from app.models.record import BookRecord, WeReadSyncState
from app.services import weread
from app.tasks import jobs


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _settings(api_key: str = "wrk-test", enabled: bool = True):
    return SimpleNamespace(
        WEREAD_API_KEY=api_key,
        WEREAD_SYNC_ENABLED=enabled,
        WEREAD_SYNC_INTERVAL_MINUTES=30,
        WEREAD_SKILL_VERSION="1.0.3",
        WEREAD_GATEWAY_URL="https://i.weread.qq.com/api/agent/gateway",
        WEREAD_SYNC_LOCK_SECONDS=900,
    )


def test_gateway_body_keeps_business_params_flat() -> None:
    body = weread._build_gateway_body("/user/notebooks", "1.0.3", {"count": 100, "lastSort": 123})

    assert body == {
        "api_name": "/user/notebooks",
        "skill_version": "1.0.3",
        "count": 100,
        "lastSort": 123,
    }
    assert "params" not in body


def test_fetch_all_notebooks_uses_last_sort_pagination() -> None:
    class FakeClient:
        def __init__(self):
            self.calls = []

        def call(self, api_name: str, **params):
            self.calls.append((api_name, params))
            if len(self.calls) == 1:
                return {"books": [{"bookId": "1", "sort": 88}], "hasMore": 1}
            return {"books": [{"bookId": "2", "sort": 77}], "hasMore": 0}

    client = FakeClient()
    books = weread._fetch_all_notebooks(client, count=100)

    assert [item["bookId"] for item in books] == ["1", "2"]
    assert client.calls == [
        ("/user/notebooks", {"count": 100}),
        ("/user/notebooks", {"count": 100, "lastSort": 88}),
    ]


def test_duration_and_note_count_follow_official_units() -> None:
    assert weread._seconds_to_duration(3720) == "1小时2分钟"
    assert weread._calculate_note_count({"reviewCount": 2, "noteCount": 3, "bookmarkCount": 4}) == 9


def test_sync_without_api_key_marks_not_configured() -> None:
    db = _session()

    result = weread.sync_weread_records(db, _settings(api_key=""))
    state = db.query(WeReadSyncState).filter(WeReadSyncState.key == "weread").first()

    assert result.status == "not_configured"
    assert result.skipped is True
    assert state is not None
    assert state.status == "not_configured"


def test_failed_sync_does_not_clear_existing_records(monkeypatch) -> None:
    db = _session()
    db.add(BookRecord(source="weread", source_id="book-1", title="Existing", is_in_shelf=True))
    db.commit()

    class FailingClient:
        def __init__(self, _cfg):
            pass

        def call(self, api_name: str, **_params):
            raise weread.WeReadGatewayError(f"{api_name} failed")

    monkeypatch.setattr(weread, "WeReadGatewayClient", FailingClient)
    monkeypatch.setattr(weread, "_acquire_sync_lock", lambda _cfg: "lock-token")
    monkeypatch.setattr(weread, "_release_sync_lock", lambda _token: None)

    result = weread.sync_weread_records(db, _settings())
    record = db.query(BookRecord).filter(BookRecord.source_id == "book-1").one()

    assert result.status == "failed"
    assert record.title == "Existing"
    assert record.is_in_shelf is True


def test_sync_preserves_admin_visibility_for_existing_private_weread_book(monkeypatch) -> None:
    db = _session()
    db.add(BookRecord(
        source="weread",
        source_id="book-1",
        title="Existing",
        is_in_shelf=True,
        is_private=False,
        visibility="login",
    ))
    db.commit()

    class FakeClient:
        def __init__(self, _cfg):
            pass

        def call(self, api_name: str, **_params):
            if api_name == "/shelf/sync":
                return {
                    "books": [
                        {
                            "bookId": "book-1",
                            "title": "Existing",
                            "author": "Author",
                            "secret": 1,
                            "finishReading": 0,
                        }
                    ]
                }
            if api_name == "/readdata/detail":
                return {}
            if api_name == "/user/notebooks":
                return {"books": [], "hasMore": 0}
            if api_name == "/book/getprogress":
                return {"book": {"progress": 12, "recordReadingTime": 600}}
            raise AssertionError(f"unexpected call: {api_name}")

    monkeypatch.setattr(weread, "WeReadGatewayClient", FakeClient)
    monkeypatch.setattr(weread, "_acquire_sync_lock", lambda _cfg: "lock-token")
    monkeypatch.setattr(weread, "_release_sync_lock", lambda _token: None)

    result = weread.sync_weread_records(db, _settings())
    record = db.query(BookRecord).filter(BookRecord.source_id == "book-1").one()

    assert result.status == "success"
    assert record.is_private is True
    assert record.visibility == "login"


def test_sync_defaults_new_weread_books_to_admin_visibility(monkeypatch) -> None:
    db = _session()

    class FakeClient:
        def __init__(self, _cfg):
            pass

        def call(self, api_name: str, **_params):
            if api_name == "/shelf/sync":
                return {
                    "books": [
                        {
                            "bookId": "book-new",
                            "title": "New Book",
                            "author": "Author",
                            "secret": 0,
                            "finishReading": 0,
                        }
                    ]
                }
            if api_name == "/readdata/detail":
                return {}
            if api_name == "/user/notebooks":
                return {"books": [], "hasMore": 0}
            if api_name == "/book/getprogress":
                return {"book": {"progress": 8, "recordReadingTime": 300}}
            raise AssertionError(f"unexpected call: {api_name}")

    monkeypatch.setattr(weread, "WeReadGatewayClient", FakeClient)
    monkeypatch.setattr(weread, "_acquire_sync_lock", lambda _cfg: "lock-token")
    monkeypatch.setattr(weread, "_release_sync_lock", lambda _token: None)

    result = weread.sync_weread_records(db, _settings())
    record = db.query(BookRecord).filter(BookRecord.source_id == "book-new").one()

    assert result.status == "success"
    assert record.is_private is False
    assert record.visibility == "private"


def test_sync_lock_release_only_deletes_own_token(monkeypatch) -> None:
    class FakeRedis:
        def __init__(self):
            self.value = None
            self.deleted = False

        def set(self, key, value, ex=None, nx=False):
            if nx and self.value is not None:
                return False
            self.value = value
            return True

        def get(self, key):
            return self.value

        def delete(self, key):
            self.deleted = True
            self.value = None

    client = FakeRedis()
    monkeypatch.setattr(weread.redis_client, "get_client", lambda: client)

    token = weread._acquire_sync_lock(_settings())
    assert token

    client.value = "new-owner"
    weread._release_sync_lock(token)

    assert client.value == "new-owner"
    assert client.deleted is False


def test_book_time_stats_uses_weread_readdata_without_leaking_private_books() -> None:
    state = WeReadSyncState(
        key="weread",
        stats_json=json.dumps({
            "readTimes": {"1777651200": 1800, "1777737600": 3600},
            "totalReadTime": 5400,
            "dayAverageReadTime": 2700,
            "readDays": 2,
            "compare": 0.25,
            "preferCategory": [
                {"categoryTitle": "经济", "parentCategoryTitle": "社科", "readingCount": 2, "readingTime": 3600},
            ],
            "readLongest": [
                {"book": {"bookId": "public-book", "title": "Public"}, "readTime": 2400, "tags": ["经济"]},
                {"book": {"bookId": "private-book", "title": "Private"}, "readTime": 3000, "tags": ["私密"]},
                {"book": {"title": "No Source Id"}, "readTime": 1200, "tags": ["未知"]},
            ],
        }, ensure_ascii=False),
    )
    records = [
        BookRecord(
            source="weread",
            source_id="public-book",
            title="公开书",
            author="作者",
            is_in_shelf=True,
            is_private=False,
            note_count=3,
            tags_json='["经济", "微信读书"]',
        )
    ]

    stats = weread.book_time_stats_to_dict(state, records)

    assert stats["total_read_seconds"] == 5400
    assert stats["total_read_duration"] == "1小时30分钟"
    assert stats["day_average_duration"] == "45分钟"
    assert [item["read_seconds"] for item in stats["daily"]] == [1800, 3600]
    assert stats["categories"][0]["percent"] == 67
    assert [item["title"] for item in stats["longest_books"]] == ["公开书"]


def test_book_time_stats_can_hide_breakdowns_while_keeping_aggregate_time() -> None:
    state = WeReadSyncState(
        key="weread",
        stats_json=json.dumps({
            "readTimes": {"1777651200": 1800},
            "totalReadTime": 1800,
            "dayAverageReadTime": 1800,
            "readDays": 1,
            "preferCategory": [
                {"categoryTitle": "私密分类", "readingCount": 1, "readingTime": 1800},
            ],
            "readLongest": [
                {"book": {"bookId": "private-book", "title": "Private"}, "readTime": 1800},
            ],
        }, ensure_ascii=False),
    )

    stats = weread.book_time_stats_to_dict(state, [], include_breakdowns=False)

    assert stats["total_read_seconds"] == 1800
    assert stats["daily"][0]["read_seconds"] == 1800
    assert stats["categories"] == []
    assert stats["longest_books"] == []


def test_weread_job_registration_requires_enabled_api_key(monkeypatch) -> None:
    monkeypatch.setattr(jobs.settings, "WEREAD_SYNC_ENABLED", True)
    monkeypatch.setattr(jobs.settings, "WEREAD_API_KEY", "")
    assert jobs._should_register_weread_job() is False

    monkeypatch.setattr(jobs.settings, "WEREAD_API_KEY", "wrk-test")
    assert jobs._should_register_weread_job() is True

    monkeypatch.setattr(jobs.settings, "WEREAD_SYNC_ENABLED", False)
    assert jobs._should_register_weread_job() is False
