from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine

from bia.agents.registry import get_agent_detail
from bia.agents.repository import AgentNotFoundError, get_agent, list_agents, lock_agent
from bia.database.connection import database_session
from bia.database.migrate import apply_schema
from tests.tracing.seed import insert_agent


@pytest.fixture
def connection(integration_engine: Engine) -> Iterator[Connection]:
    """Provides a connection with the schema, rolled back at the end.

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


def test_list_and_get_read_the_stored_identity(connection: Connection) -> None:
    """Verifies the rows of the table satisfy the contract, without selecting the embedding."""
    agent_id = insert_agent(connection)

    with database_session(connection) as session:
        listed = {agent.id for agent in list_agents(session)}
        agent = get_agent(session, agent_id)

    assert agent_id in listed
    assert agent.name == "Test agent"
    assert "description_embedding" not in agent.model_dump()


@pytest.mark.parametrize("read", [get_agent, lock_agent])
def test_reads_of_one_agent_name_the_identifier_they_could_not_find(
    connection: Connection, read: object
) -> None:
    """Verifies a wrong identifier is a clear error in both the plain and the locking read."""
    missing_id = uuid4()

    with (
        database_session(connection) as session,
        pytest.raises(AgentNotFoundError, match=str(missing_id)),
    ):
        read(session, missing_id)


def test_detail_of_an_agent_without_versions_has_no_active_version(connection: Connection) -> None:
    """Verifies rows created by hand can be read instead of failing as if they did not exist."""
    agent_id = insert_agent(connection)

    with database_session(connection) as session:
        detail = get_agent_detail(session, agent_id)

    assert detail.agent.id == agent_id
    assert detail.active_version is None
