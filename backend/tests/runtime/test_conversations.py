from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine

from bia.agents.artifacts import AgentSpec
from bia.database.connection import database_session
from bia.database.migrate import apply_schema
from bia.providers.base import ProviderError
from bia.runtime import conversations
from bia.runtime.conversations import (
    ConversationNotOpenError,
    continue_conversation,
    finish_conversation,
    start_conversation,
)
from bia.tracing.artifacts import RunOrigin, RunRecord, RunStatus
from bia.tracing.recorder import RunRecorder
from bia.tracing.repository import RunNotFoundError, get_run
from tests.providers.fake import FakeModelProvider
from tests.tracing.seed import insert_active_version, insert_agent, insert_model


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


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeModelProvider:
    """Provides the scripted provider that conversations will use.

    Args:
        monkeypatch: Replaces the provider factory of the module.

    Returns:
        FakeModelProvider: the provider, with nothing scripted.
    """
    fake = FakeModelProvider()
    monkeypatch.setattr(conversations, "get_provider", lambda _name: fake)
    return fake


def _new_agent(connection: Connection, system_prompt: str = "Eres útil") -> UUID:
    """Creates an agent with an active version.

    Args:
        connection: The connection of the test's transaction.
        system_prompt: The instructions of the version.

    Returns:
        UUID: the identifier of the agent.
    """
    agent_id = insert_agent(connection)
    _add_version(connection, agent_id, system_prompt, 1)
    return agent_id


def _add_version(
    connection: Connection, agent_id: UUID, system_prompt: str, version_number: int
) -> None:
    """Activates a new version of an agent.

    Args:
        connection: The connection of the test's transaction.
        agent_id: The agent.
        system_prompt: The instructions of the version.
        version_number: The number of the version.
    """
    spec = AgentSpec(purpose="p", system_prompt=system_prompt, model_id=insert_model(connection))
    insert_active_version(connection, agent_id, spec.model_dump_json(), version_number)


def _read_run(connection: Connection, run_id: UUID) -> RunRecord:
    """Reads a run with its steps.

    Args:
        connection: The connection of the test's transaction.
        run_id: The run.

    Returns:
        RunRecord: the run.
    """
    with database_session(connection) as session:
        return get_run(session, run_id)


def test_follow_up_stays_in_the_same_run_and_remembers_the_conversation(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the behavior asked for: one run per conversation, with memory across messages."""
    agent_id = _new_agent(connection)
    provider.queue_text("Te llamas Ana")
    provider.queue_text("Ana")

    first = start_conversation(connection, agent_id, "Me llamo Ana")
    second = continue_conversation(connection, agent_id, first.run_id, "¿Cómo me llamo?")

    assert second.run_id == first.run_id
    assert second.status is RunStatus.RUNNING
    sent = [(message.role.value, message.content) for message in provider.chat_requests[1]]
    assert sent == [
        ("system", "Eres útil"),
        ("user", "Me llamo Ana"),
        ("assistant", "Te llamas Ana"),
        ("user", "¿Cómo me llamo?"),
    ]
    run = _read_run(connection, first.run_id)
    assert (run.input, run.output) == ("Me llamo Ana", "Ana")
    assert (run.total_tokens, len(run.steps)) == (30, 2)


def test_after_finishing_the_next_message_opens_a_new_run_without_memory(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies finishing closes the run, rejects late messages and starts the next one clean."""
    agent_id = _new_agent(connection)
    provider.queue_text("Hola Ana")
    provider.queue_text("No lo sé")
    first = start_conversation(connection, agent_id, "Me llamo Ana")

    closed = finish_conversation(connection, first.run_id)
    with pytest.raises(ConversationNotOpenError):
        continue_conversation(connection, agent_id, first.run_id, "tarde")
    second = start_conversation(connection, agent_id, "¿Cómo me llamo?")

    assert (closed.status, closed.output) == (RunStatus.SUCCEEDED, "Hola Ana")
    assert second.run_id != first.run_id
    assert "Me llamo Ana" not in [message.content for message in provider.chat_requests[1]]


def test_conversation_recovers_from_a_failed_first_turn(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the person can retry in the same run, and the failure stays in its trace."""
    agent_id = _new_agent(connection)
    provider.queue_chat_error(ProviderError("timeout"))
    provider.queue_text("Ahora sí")

    failed = start_conversation(connection, agent_id, "Hola")
    retried = continue_conversation(connection, agent_id, failed.run_id, "Hola otra vez")

    assert (failed.status, failed.output) == (RunStatus.RUNNING, None)
    assert "timeout" in failed.error
    assert retried.output == "Ahora sí"
    assert [step.error is None for step in _read_run(connection, failed.run_id).steps] == [
        False,
        True,
    ]


def test_conversation_keeps_the_version_it_started_with(
    connection: Connection, provider: FakeModelProvider
) -> None:
    """Verifies the trace stays true when the agent activates another version meanwhile."""
    agent_id = _new_agent(connection, "Versión uno")
    provider.queue_text("Uno")
    provider.queue_text("Dos")
    first = start_conversation(connection, agent_id, "Hola")
    _add_version(connection, agent_id, "Versión dos", 2)

    continue_conversation(connection, agent_id, first.run_id, "Sigue")

    assert provider.chat_requests[1][0].content == "Versión uno"


def test_runs_that_are_not_open_conversations_cannot_be_altered(connection: Connection) -> None:
    """Verifies the playground cannot write into an eval in progress, or into another agent."""
    agent_id = _new_agent(connection)
    with database_session(connection) as session:
        version_id = conversations.load_agent_execution(session, agent_id).version.id
    recorder = RunRecorder(connection)
    eval_run = recorder.start_run(agent_id, version_id, RunOrigin.EVAL, "caso")
    open_run = recorder.start_run(agent_id, version_id, RunOrigin.PLAYGROUND, "hola")

    with pytest.raises(ConversationNotOpenError):
        finish_conversation(connection, eval_run.id)
    with pytest.raises(ConversationNotOpenError):
        continue_conversation(connection, agent_id, eval_run.id, "x")
    with pytest.raises(ConversationNotOpenError):
        continue_conversation(connection, uuid4(), open_run.id, "x")
    with pytest.raises(RunNotFoundError):
        finish_conversation(connection, uuid4())
