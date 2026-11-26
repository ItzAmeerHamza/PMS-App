"""SQLite engine, sessions, and connection settings.

Schema changes live in ``backend/migrations`` (Alembic). This module never creates
or alters tables; see ``core/migrate.py`` for the startup upgrade.
"""

from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .paths import database_path

Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False)

_engine: Engine | None = None


def _sqlite_pragmas(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def init_engine(path: Path | None = None) -> Engine:
    """Create the engine for ``path`` (default: the configured data dir) and bind sessions to it."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    db_file = Path(path) if path else database_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        # SQL errors must not echo row values (patient names, phones) into logs.
        hide_parameters=True,
    )
    event.listen(engine, "connect", _sqlite_pragmas)
    SessionLocal.configure(bind=engine)
    _engine = engine
    return engine


def get_engine() -> Engine:
    if _engine is None:
        return init_engine()
    return _engine


def engine_path() -> Path:
    return Path(get_engine().url.database)


def get_db(request: Request):
    """One session per request, closed afterwards.

    The signed-in staff id and that manager's pharmacy (set by the auth middleware)
    ride on the session, so audit rows know who acted and services can scope
    reads and writes to the signed-in pharmacy.
    """
    get_engine()
    db = SessionLocal()
    db.info["staff_id"] = getattr(request.state, "staff_id", None)
    db.info["pharmacy_id"] = getattr(request.state, "pharmacy_id", None)
    try:
        yield db
    finally:
        db.close()
