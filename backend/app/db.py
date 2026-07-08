import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

# Default to a repo-root SQLite file for zero-config local development.
DEFAULT_SQLITE_URL = f"sqlite:///{Path(__file__).resolve().parent.parent.parent / 'macros.db'}"

_engine: Engine | None = None


def get_database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)


def get_engine() -> Engine:
    # Built lazily so tests can point DATABASE_URL at a temp database before
    # the first connection is made; dispose_engine() resets between tests.
    global _engine
    if _engine is None:
        url = get_database_url()
        if url.startswith("sqlite"):
            # TestClient runs endpoints on a worker thread.
            _engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            # Neon autosuspends idle computes; pre-ping replaces dead connections.
            _engine = create_engine(
                url, pool_pre_ping=True, pool_size=5, max_overflow=5
            )
    return _engine


def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


@event.listens_for(Engine, "connect")
def _sqlite_enable_foreign_keys(dbapi_connection, _connection_record) -> None:
    # SQLite ships with FK enforcement off; without this, CASCADE and FK
    # integrity would silently differ between tests (SQLite) and prod (Postgres).
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session; endpoints commit explicitly."""
    with Session(get_engine()) as session:
        yield session
