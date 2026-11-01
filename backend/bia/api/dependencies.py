from collections.abc import Iterator

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
