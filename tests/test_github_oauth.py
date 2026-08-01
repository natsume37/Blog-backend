import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base
from app.models.user import User
from app.routers import auth


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_safe_frontend_path_blocks_external_redirects() -> None:
    assert auth._safe_frontend_path("/admin?tab=1") == "/admin?tab=1"
    assert auth._safe_frontend_path("https://evil.example") == "/"
    assert auth._safe_frontend_path("//evil.example/path") == "/"
    assert auth._safe_frontend_path("/safe\r\nLocation: https://evil.example") == "/"


def test_github_user_links_existing_verified_email() -> None:
    db = _session()
    db.add(User(
        username="martin",
        email="martin@example.com",
        hashed_password="hash",
        nickname="Martin",
        is_active=True,
        is_admin=True,
    ))
    db.commit()

    user = auth._get_or_create_github_user(
        db,
        {
            "id": 123,
            "login": "martin-gh",
            "name": "Martin GitHub",
            "avatar_url": "https://avatars.githubusercontent.com/u/123",
        },
        "martin@example.com",
    )

    assert user.username == "martin"
    assert user.github_id == "123"
    assert user.github_login == "martin-gh"
    assert user.is_admin is True


def test_github_user_without_verified_email_does_not_take_existing_email() -> None:
    db = _session()
    db.add(User(
        username="existing",
        email="public@example.com",
        hashed_password="hash",
        nickname="Existing",
        is_active=True,
        is_admin=False,
    ))
    db.commit()

    user = auth._get_or_create_github_user(
        db,
        {
            "id": 456,
            "login": "octo-cat",
            "name": "Octo Cat",
            "email": "public@example.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/456",
        },
        None,
    )

    assert user.username == "github_octo_cat"
    assert user.email == "github-456@users.noreply.github.local"
    assert user.github_id == "456"
    assert user.is_admin is False


def test_owner_only_github_login_does_not_create_accounts() -> None:
    db = _session()

    try:
        auth._get_or_create_github_user(
            db,
            {"id": 789, "login": "visitor"},
            None,
            allow_create=False,
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("owner-only mode must not create GitHub accounts")

    assert db.query(User).count() == 0


def test_verified_email_link_rejects_different_existing_github_id() -> None:
    db = _session()
    db.add(User(
        username="linked",
        email="linked@example.com",
        hashed_password="hash",
        nickname="Linked",
        github_id="old-id",
        is_active=True,
        is_admin=False,
    ))
    db.commit()

    try:
        auth._get_or_create_github_user(
            db,
            {"id": "new-id", "login": "new-login", "name": "New Login"},
            "linked@example.com",
        )
    except ValueError as exc:
        assert "already linked" in str(exc)
    else:
        raise AssertionError("verified email linked to another GitHub id should fail")
