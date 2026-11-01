from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine

from bia.database.connection import database_session
from bia.database.migrate import apply_schema, apply_seeds
from bia.rag import ingestion, retrieval
from tests.providers.fake import FakeModelProvider

_EMBEDDING_DIMENSIONS = 1536


@pytest.fixture
def connection(integration_engine: Engine) -> Iterator[Connection]:
    """Provides a connection with the schema and the seeded catalog, rolled back at the end.

    Args:
        integration_engine: The engine of the real database.

    Returns:
        Iterator[Connection]: yields the connection inside the open transaction.
    """
    with integration_engine.connect() as open_connection:
        transaction = open_connection.begin()
        with database_session(open_connection) as session:
            apply_schema(session)
            apply_seeds(session)
        yield open_connection
        transaction.rollback()


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeModelProvider:
    """Replaces the provider of the ingestion and the search with one at the real dimensions.

    Args:
        monkeypatch: The patcher of both modules.

    Returns:
        FakeModelProvider: the provider they will use.
    """
    fake = FakeModelProvider(embedding_dimensions=_EMBEDDING_DIMENSIONS)
    monkeypatch.setattr(ingestion, "get_provider", lambda _name: fake)
    monkeypatch.setattr(retrieval, "get_provider", lambda _name: fake)
    return fake
