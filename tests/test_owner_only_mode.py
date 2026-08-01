import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import deps
from app.core.config import settings
from app.core.database import Base
from app.core.security import create_access_token
from app.main import app
from app.models.user import User


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def _user(*, username: str, is_admin: bool) -> User:
    return User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="hash",
        nickname=username,
        is_active=True,
        is_admin=is_admin,
    )


def test_owner_only_dependency_rejects_non_admin_session(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OWNER_ONLY_MODE", True)
    db = _session()
    visitor = _user(username="visitor", is_admin=False)
    db.add(visitor)
    db.commit()
    token = create_access_token({"sub": str(visitor.id)})

    with pytest.raises(HTTPException) as error:
        deps.get_current_user(db=db, request=None, token=token)

    assert error.value.status_code == 401
    assert deps.get_optional_current_user(db=db, request=None, token=token) is None


def test_owner_only_dependency_accepts_admin_session(monkeypatch) -> None:
    monkeypatch.setattr(settings, "OWNER_ONLY_MODE", True)
    db = _session()
    owner = _user(username="owner", is_admin=True)
    db.add(owner)
    db.commit()
    token = create_access_token({"sub": str(owner.id)})

    current = deps.get_current_user(db=db, request=None, token=token)

    assert current.id == owner.id


def test_public_interactions_are_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "PUBLIC_INTERACTIONS_ENABLED", False)

    with pytest.raises(HTTPException) as error:
        deps.require_public_interactions_enabled()

    assert error.value.status_code == 403
    assert "只读" in error.value.detail


def test_comment_and_message_routers_are_not_published() -> None:
    published_paths = set(app.openapi()["paths"])

    assert not any(path.startswith("/api/v1/comments") for path in published_paths)
    assert not any(path.startswith("/api/v1/messages") for path in published_paths)


def _route_dependencies(path: str, method: str) -> set[object]:
    route = next(
        route
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in route.methods
    )
    return {dependency.call for dependency in route.dependant.dependencies}


def test_costly_and_persistent_write_endpoints_require_admin() -> None:
    assert deps.get_current_admin in _route_dependencies("/api/v1/resources", "POST")
    assert deps.get_current_admin in _route_dependencies("/api/v1/ai/mcp/call", "POST")


def test_record_write_endpoints_require_admin() -> None:
    for path in ("/api/v2/records/notes", "/api/v2/records/focus", "/api/v2/records/reading", "/api/v2/records/movies"):
        assert deps.get_current_admin in _route_dependencies(path, "POST")
