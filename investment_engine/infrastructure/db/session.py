from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from ..config import settings


def make_engine(database_url: str | None = None, *, echo: bool | None = None):
    url = database_url or settings.database_url
    options = {
        "echo": settings.database_echo if echo is None else echo,
        "pool_pre_ping": True,
    }
    # The Oracle Micro host has 1 GB of RAM and PostgreSQL is configured for a
    # small number of clients. Keep the reusable application pool bounded.
    # Non-PostgreSQL URLs used by isolated tests retain SQLAlchemy defaults.
    if str(url).startswith(("postgresql://", "postgresql+psycopg://")):
        options.update(
            pool_size=max(1, min(20, int(settings.database_pool_size))),
            max_overflow=max(0, min(20, int(settings.database_max_overflow))),
            pool_timeout=max(1, int(settings.database_pool_timeout_seconds)),
            pool_recycle=max(60, int(settings.database_pool_recycle_seconds)),
            connect_args={
                "options": f"-c statement_timeout={max(1000, int(settings.database_statement_timeout_ms))}",
            },
        )
    return create_engine(url, **options)


@lru_cache(maxsize=1)
def get_engine():
    return make_engine()


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, class_=Session)


@contextmanager
def session_scope():
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
