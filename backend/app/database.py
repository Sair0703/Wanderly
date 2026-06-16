"""Database engine and session management (SQLAlchemy 2.0)."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


def _normalize_db_url(url: str) -> str:
    """Managed hosts (Render/Railway/Heroku) expose ``postgres://``; SQLAlchemy
    needs an explicit driver. Normalize to psycopg2."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


DATABASE_URL = _normalize_db_url(settings.database_url)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # Allow SQLite use across FastAPI's threadpool.
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. Models must be imported before calling."""
    from . import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
