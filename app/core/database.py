from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings


def build_engine_kwargs(database_url: str) -> dict:
    """Build conservative SQLAlchemy engine options for the configured backend."""
    url = make_url(database_url)
    kwargs = {
        "pool_pre_ping": True,
        "echo": settings.DEBUG,
    }

    if url.get_backend_name() != "sqlite":
        kwargs.update(
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_recycle=3600,
        )

    return kwargs


engine = create_engine(settings.DATABASE_URL, **build_engine_kwargs(settings.DATABASE_URL))

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
