"""Engine and sessions. One session per request."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from ..config import get_settings

SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)
_engine: Engine | None = None


def init_engine(url: str | None = None) -> Engine:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url or get_settings().sqlalchemy_url, pool_pre_ping=True, hide_parameters=True)
    SessionLocal.configure(bind=_engine)
    return _engine


def get_engine() -> Engine:
    return _engine or init_engine()


def get_db():
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
