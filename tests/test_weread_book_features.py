import sys
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base
from app.models.record import BookNoteCache, BookRecord, BookSearchCache
from app.services import weread


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _settings(api_key: str = "wrk-test"):
    return SimpleNamespace(
        WEREAD_API_KEY=api_key,
        WEREAD_SYNC_ENABLED=True,
        WEREAD_SYNC_INTERVAL_MINUTES=30,
        WEREAD_SKILL_VERSION="1.0.3",
        WEREAD_GATEWAY_URL="https://i.weread.qq.com/api/agent/gateway",
        WEREAD_SYNC_LOCK_SECONDS=900,
    )


def test_search_weread_books_parses_and_caches_results(monkeypatch) -> None:
    db = _session()

    class FakeClient:
        def __init__(self, _cfg):
            pass

        def call(self, api_name: str, **params):
            assert api_name == "/store/search"
            assert params["keyword"] == "三体"
            return {
                "results": [
                    {
                        "books": [
                            {
                                "readingCount": 1200,
                                "newRating": 92,
                                "newRatingCount": 300,
                                "bookInfo": {
                                    "bookId": "book-1",
                                    "title": "三体",
                                    "author": "刘慈欣",
                                    "cover": "https://example.com/cover.jpg",
                                    "intro": "科幻长篇",
                                    "publisher": "重庆出版社",
                                    "category": "科幻",
                                },
                            }
                        ]
                    }
                ]
            }

    monkeypatch.setattr(weread, "WeReadGatewayClient", FakeClient)

    data, message = weread.search_weread_books(db, _settings(), "三体")
    cached = db.query(BookSearchCache).filter(BookSearchCache.source_id == "book-1").one()

    assert message == "success"
    assert data[0]["title"] == "三体"
    assert data[0]["rating"] == 4.6
    assert cached.title == "三体"
    assert cached.rating == 92


def test_detail_fetch_merges_weread_detail_with_local_record(monkeypatch) -> None:
    db = _session()
    db.add(BookRecord(source="weread", source_id="book-1", title="Old", is_in_shelf=True, visibility="public"))
    db.commit()

    class FakeClient:
        def __init__(self, _cfg):
            pass

        def call(self, api_name: str, **_params):
            if api_name == "/book/info":
                return {
                    "bookId": "book-1",
                    "title": "三体",
                    "author": "刘慈欣",
                    "publisher": "重庆出版社",
                    "isbn": "9787229008",
                    "wordCount": 300000,
                    "newRating": 94,
                    "newRatingCount": 600,
                }
            if api_name == "/book/getprogress":
                return {"book": {"progress": 45, "recordReadingTime": 3600, "updateTime": 1777651200}}
            if api_name == "/book/chapterinfo":
                return {"chapters": [{"chapterUid": 101, "chapterIdx": 1, "title": "科学边界", "wordCount": 8000}]}
            raise AssertionError(api_name)

    monkeypatch.setattr(weread, "WeReadGatewayClient", FakeClient)

    data, message = weread.get_weread_book_detail(db, _settings(), "book-1")
    record = db.query(BookRecord).filter(BookRecord.source_id == "book-1").one()

    assert message == "success"
    assert data["title"] == "三体"
    assert data["progress"] == 45
    assert data["chapters"][0]["deep_link"] == "weread://reading?bId=book-1&chapterUid=101"
    assert record.publisher == "重庆出版社"
    assert record.chapter_count == 1


def test_notes_fetch_combines_highlights_and_reviews(monkeypatch) -> None:
    db = _session()
    db.add(BookRecord(source="weread", source_id="book-1", title="三体", is_in_shelf=True, visibility="private"))
    db.commit()

    class FakeClient:
        def __init__(self, _cfg):
            pass

        def call(self, api_name: str, **_params):
            if api_name == "/book/bookmarklist":
                return {
                    "chapters": [{"chapterUid": 101, "title": "科学边界"}],
                    "updated": [
                        {
                            "bookmarkId": "mark-1",
                            "chapterUid": 101,
                            "markText": "物理学从来就没有存在过。",
                            "range": "10-18",
                            "createTime": 1777651200,
                        }
                    ],
                }
            if api_name == "/review/list/mine":
                return {
                    "reviews": [
                        {
                            "review": {
                                "reviewId": "review-1",
                                "content": "这一段适合回看。",
                                "chapterName": "科学边界",
                                "createTime": 1777651300,
                            }
                        }
                    ],
                    "hasMore": 0,
                }
            raise AssertionError(api_name)

    monkeypatch.setattr(weread, "WeReadGatewayClient", FakeClient)

    data, message = weread.fetch_weread_book_notes(db, _settings(), "book-1")
    cached_count = db.query(BookNoteCache).count()

    assert message == "success"
    assert data["total"] == 2
    assert data["highlight_count"] == 1
    assert data["review_count"] == 1
    assert cached_count == 2


def test_local_recommendations_are_rule_based_and_stable() -> None:
    records = [
        BookRecord(source="weread", source_id="low", title="Low", progress=0, rating=20, note_count=0, read_seconds=0),
        BookRecord(source="weread", source_id="active", title="Active", progress=55, rating=40, note_count=10, read_seconds=3600),
        BookRecord(source="weread", source_id="top", title="Top", progress=100, rating=50, note_count=20, read_seconds=7200),
    ]

    recommendations = weread.build_local_book_recommendations(records, limit=2)

    assert [item["source_id"] for item in recommendations] == ["top", "active"]
    assert recommendations[0]["reason"]
