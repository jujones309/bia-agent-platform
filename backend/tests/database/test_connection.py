import pytest
from sqlalchemy import Engine, column, create_engine, insert, literal, select, table
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import Column, MetaData, Table
from sqlalchemy.types import Integer

from bia.database.connection import create_database_engine, database_session

_ITEMS = table("items", column("value"))


@pytest.fixture
def sqlite_engine() -> Engine:
    """Builds an in-memory database with one empty table, to observe real transactions.

    Returns:
        Engine: an engine whose connections all share the same in-memory database.
    """
    engine = create_engine("sqlite://", poolclass=StaticPool)
    metadata = MetaData()
    Table("items", metadata, Column("value", Integer))
    metadata.create_all(engine)
    return engine


def _count_items(engine: Engine) -> int:
    """Counts the committed rows of the test table, from a new session.

    Args:
        engine: The engine of the test database.

    Returns:
        int: the number of rows.
    """
    with database_session(engine) as session:
        return len(session.execute(select(_ITEMS)).all())


def test_session_commits_when_the_block_succeeds(sqlite_engine: Engine) -> None:
    """Verifies callers do not need to commit by hand."""
    with database_session(sqlite_engine) as session:
        session.execute(insert(_ITEMS).values(value=1))

    assert _count_items(sqlite_engine) == 1


def test_session_rolls_back_and_propagates_when_the_block_fails(sqlite_engine: Engine) -> None:
    """Verifies a failure leaves no partial writes and is not swallowed."""
    with pytest.raises(ValueError, match="boom"), database_session(sqlite_engine) as session:
        session.execute(insert(_ITEMS).values(value=1))
        raise ValueError("boom")

    assert _count_items(sqlite_engine) == 0


@pytest.mark.parametrize("scheme", ["postgresql", "postgresql+psycopg2"])
def test_engine_always_uses_psycopg(scheme: str) -> None:
    """Verifies Supabase's plain URL works, since the default driver is not installed."""
    engine = create_database_engine(f"{scheme}://user:password@localhost:6543/db")

    assert engine.url.drivername == "postgresql+psycopg"


def test_engine_connects_to_the_real_database(integration_engine: Engine) -> None:
    """Verifies the engine works against Postgres through the configured pooler."""
    with database_session(integration_engine) as session:
        assert session.scalar(select(literal(1))) == 1
