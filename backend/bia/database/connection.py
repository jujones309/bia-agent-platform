from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from bia.settings.config import get_settings

_PSYCOPG_DRIVER = "postgresql+psycopg"


def create_database_engine(database_url: str) -> Engine:
    """Builds an engine compatible with Supabase's transaction pooler.

    Exists to keep the pooler's constraints in one place: the pooler owns connection
    pooling and does not support prepared statements, so both are disabled on the client.
    Used by `get_engine` and by integration tests.

    Args:
        database_url: The connection string, with or without an explicit driver.

    Returns:
        Engine: an engine that connects through psycopg.
    """
    url = make_url(database_url).set(drivername=_PSYCOPG_DRIVER)
    return create_engine(url, poolclass=NullPool, connect_args={"prepare_threshold": None})


@lru_cache
def get_engine() -> Engine:
    """Retrieves the process-wide engine, creating it on first use.

    Exists so every vertical shares one engine built from the settings; used by the
    verticals that open database sessions.

    Returns:
        Engine: the cached engine.
    """
    return create_database_engine(get_settings().database_url.get_secret_value())


@contextmanager
def database_session(engine: Engine) -> Iterator[Session]:
    """Opens a session whose work is committed together or not at all.

    Exists so callers never manage transactions by hand: leaving the block commits, and
    an exception rolls back and propagates. Used by every vertical that touches the database.

    Args:
        engine: The engine to connect through.

    Returns:
        Iterator[Session]: yields the session bound to the open transaction.
    """
    with Session(engine) as session, session.begin():
        yield session
