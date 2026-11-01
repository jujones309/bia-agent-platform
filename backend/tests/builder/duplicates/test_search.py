from collections.abc import Iterator
from uuid import UUID

import pytest
from sqlalchemy import Connection, Engine, Uuid, column, table, update

from bia.agents.artifacts import AgentKind, AgentStatus
from bia.builder.artifacts import DuplicateCandidate
from bia.builder.duplicates.search import find_candidates
from bia.database.connection import database_session
from bia.database.migrate import apply_schema, apply_seeds
from tests.builder.duplicates.seed import (
    hide_published_agents,
    insert_registered_agent,
    unit_vector,
)

_AGENTS = table("agents", column("id", Uuid), column("status"), column("kind"))


@pytest.fixture
def connection(integration_engine: Engine) -> Iterator[Connection]:
    """Provides a connection with the schema and nothing published, rolled back at the end.

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
        hide_published_agents(open_connection)
        yield open_connection
        transaction.rollback()


def _search(connection: Connection, embedding: list[float]) -> list[DuplicateCandidate]:
    """Runs the search.

    Args:
        connection: The connection of the test's transaction.
        embedding: The vector of the need.

    Returns:
        list[DuplicateCandidate]: what it found.
    """
    with database_session(connection) as session:
        return find_candidates(session, embedding)


def _set_status(connection: Connection, agent_id: UUID, status: AgentStatus) -> None:
    """Changes the lifecycle state of an agent.

    Args:
        connection: The connection of the test's transaction.
        agent_id: The agent to change.
        status: The new state.

    Returns:
        None: the row is updated.
    """
    connection.execute(update(_AGENTS).where(_AGENTS.c.id == agent_id).values(status=status))


def test_search_returns_the_three_closest_published_agents_in_order(
    connection: Connection,
) -> None:
    """Verifies the limit and that the closest agent is the first the judge sees."""
    ids = [insert_registered_agent(connection, unit_vector(axis)) for axis in range(4)]
    query = [0.9, 0.3, 0.1, 0.0, *([0.0] * 1532)]

    found = _search(connection, query)

    assert [candidate.agent_id for candidate in found] == ids[:3]
    assert found[0].similarity > found[1].similarity > found[2].similarity
    assert found[0].similarity == pytest.approx(0.9438, abs=0.001)


@pytest.mark.parametrize("status", [AgentStatus.DRAFT, AgentStatus.TESTING, AgentStatus.ARCHIVED])
def test_search_leaves_out_agents_that_are_not_published(
    connection: Connection, status: AgentStatus
) -> None:
    """Verifies nobody is sent to an agent they cannot use, however close it is."""
    agent_id = insert_registered_agent(connection, unit_vector(0))
    _set_status(connection, agent_id, status)

    assert _search(connection, unit_vector(0)) == []


def test_search_leaves_out_system_agents(connection: Connection) -> None:
    """Verifies the parts of the platform are never offered as an employee's duplicate."""
    agent_id = insert_registered_agent(connection, unit_vector(0))
    connection.execute(
        update(_AGENTS).where(_AGENTS.c.id == agent_id).values(kind=AgentKind.SYSTEM)
    )

    assert _search(connection, unit_vector(0)) == []


def test_search_leaves_out_agents_without_embedding(connection: Connection) -> None:
    """Verifies a row without a vector cannot break the ordering or appear with no similarity."""
    insert_registered_agent(connection, None)

    assert _search(connection, unit_vector(0)) == []
