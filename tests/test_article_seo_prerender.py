from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.article import Article
from app.models.user import User  # noqa: F401 - 注册 articles 外键引用的 users 表
from app.routers.articles import get_article, get_articles


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def _settings() -> SimpleNamespace:
    return SimpleNamespace(is_qiniu_enabled=False)


def _article(*, title: str, is_protected: bool = False, view_count: int = 0) -> Article:
    return Article(
        title=title,
        content="正文",
        author_id=1,
        is_published=True,
        is_hidden=False,
        visibility="public",
        is_protected=is_protected,
        view_count=view_count,
    )


def test_static_prerender_does_not_increment_article_view_count() -> None:
    db = _session()
    article = _article(title="静态文章", view_count=8)
    db.add(article)
    db.commit()

    response = get_article(
        article.id,
        track_view=False,
        db=db,
        current_user=None,
        settings=_settings(),
    )

    db.refresh(article)
    assert response.code == 200
    assert response.data.viewCount == 8
    assert article.view_count == 8


def test_public_archive_query_excludes_protected_articles() -> None:
    db = _session()
    public_article = _article(title="公开文章")
    protected_article = _article(title="受保护文章", is_protected=True)
    db.add_all([public_article, protected_article])
    db.commit()

    response = get_articles(
        current=1,
        size=10,
        include_protected=False,
        db=db,
        settings=_settings(),
    )

    assert response.code == 200
    assert response.data.total == 1
    assert [item.title for item in response.data.records] == ["公开文章"]
