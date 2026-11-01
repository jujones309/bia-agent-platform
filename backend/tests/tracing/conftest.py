from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine

from bia.database.connection import database_session
from bia.database.migrate import apply_schema


@pytest.fixture
def connection(integration_engine: Engine) -> Iterator[Connection]:
    """Provides a connection whose work, including the schema, is rolled back at the end.

    Exists because the tracing queries use Postgres features and each recorder write commits
    on its own: sessions bound to this connection only commit into its outer transaction, so
    the target database stays untouched.

    Args:
        integration_engine: The engine of the real database.

    Returns:
        Iterator[Connection]: yields the connection inside the open transaction.
    """
    with integration_engine.connect() as open_connection:
        transaction = open_connection.begin()
        with database_session(open_connection) as session:
            apply_schema(session)
        yield open_connection
        transaction.rollback()
