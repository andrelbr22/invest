from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from ..config import settings


def make_engine(database_url: str | None = None, *, echo: bool | None = None):
    return create_engine(
        database_url or settings.database_url,
        echo=settings.database_echo if echo is None else echo,
        pool_pre_ping=True,
    )


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
