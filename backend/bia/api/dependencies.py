from collections.abc import Iterator

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bia.database.connection import database_session, get_engine


def get_session() -> Iterator[Session]:
    """Provides a request-scoped database session to a route.

    Exists so routers share one transaction policy and tests can replace the database by
    overriding this dependency; used through `Depends` by the routers of `bia/api/`.

    Returns:
        Iterator[Session]: yields the session, committed when the request finishes.
    """
    with database_session(get_engine()) as session:
        yield session


def get_database_engine() -> Engine:
    """Provides the engine to routes that manage their own short transactions.

    Exists because a request-scoped session would stay open for a whole agent execution,
    holding a pooler connection during every LLM call; used through `Depends` by
    `bia/api/runtime.py`.

    Returns:
        Engine: the process-wide engine.
    """
    return get_engine()
